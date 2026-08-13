#!/usr/bin/env python3
"""Manage DADS update freshness, candidate retrieval, and approved promotion."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urljoin, urlparse

from build_index import SnapshotError, atomic_write_json, scan_snapshot, sha256_file
from verify_snapshot import verify_snapshot

if os.name == "nt":
    import msvcrt
else:
    import fcntl

UTC = dt.timezone.utc
RFC3339_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
CANDIDATE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
SKILL_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR_ENV = "DADS_SKILL_STATE_DIR"


class UpstreamError(RuntimeError):
    """Raised when an update operation cannot complete safely."""


def utc_now() -> dt.datetime:
    return dt.datetime.now(tz=UTC)


def format_time(value: dt.datetime) -> str:
    return value.astimezone(UTC).strftime(RFC3339_FORMAT)


def parse_time(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("タイムゾーンがありません")
    return parsed.astimezone(UTC)


def default_state_dir() -> Path:
    configured = os.environ.get(STATE_DIR_ENV)
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData/Local"
        return base / "apply-digital-agency-design-system"
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library/Application Support/apply-digital-agency-design-system"
        )
    xdg_state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg_state_home) if xdg_state_home else Path.home() / ".local/state"
    return base / "apply-digital-agency-design-system"


def default_state_file() -> Path:
    return default_state_dir() / "update-status.json"


def load_object(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise UpstreamError(f"JSONオブジェクトではありません: {path}")
    return value


def load_state_or_default(state_file: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    if state_file.exists():
        return load_object(state_file)
    return {
        "schema_version": 1,
        "checked_contract_version": None,
        "last_attempted_at": None,
        "last_successful_check_at": None,
        "last_check_result": None,
        "source_validators": {},
        "active_snapshot_id": manifest["active_snapshot"]["id"],
        "pending_candidate_ids": [],
    }


def status_result(
    state_file: Path,
    contract_file: Path,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    current_time = (now or utc_now()).astimezone(UTC)
    try:
        contract = load_object(contract_file)
    except (OSError, json.JSONDecodeError, UpstreamError) as error:
        return {
            "ok": False,
            "status": "unknown",
            "reason": "contract_unreadable",
            "detail": str(error),
            "network_accessed": False,
        }

    if not state_file.exists():
        return {
            "ok": True,
            "status": "never_checked",
            "reason": "state_file_missing",
            "checked_at": None,
            "due_at": None,
            "network_accessed": False,
        }

    try:
        state = load_object(state_file)
        if state.get("schema_version") != 1:
            raise UpstreamError(
                f"未対応の状態スキーマです: {state.get('schema_version')!r}"
            )
        last_success_text = state.get("last_successful_check_at")
        if not last_success_text:
            return {
                "ok": True,
                "status": "never_checked",
                "reason": "successful_check_missing",
                "checked_at": None,
                "due_at": None,
                "network_accessed": False,
            }
        last_success = parse_time(last_success_text)
    except (
        OSError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        UpstreamError,
    ) as error:
        return {
            "ok": False,
            "status": "unknown",
            "reason": "state_unreadable",
            "detail": str(error),
            "network_accessed": False,
        }

    if state.get("checked_contract_version") != contract.get("contract_version"):
        return {
            "ok": True,
            "status": "unknown",
            "reason": "contract_version_changed",
            "checked_at": last_success_text,
            "due_at": None,
            "network_accessed": False,
        }
    if last_success > current_time:
        return {
            "ok": False,
            "status": "unknown",
            "reason": "successful_check_is_in_future",
            "checked_at": last_success_text,
            "due_at": None,
            "network_accessed": False,
        }

    freshness = dt.timedelta(days=int(contract["freshness_days"]))
    due_at = last_success + freshness
    is_due = current_time >= due_at
    return {
        "ok": True,
        "status": "due" if is_due else "fresh",
        "reason": "freshness_window_elapsed" if is_due else "within_freshness_window",
        "checked_at": format_time(last_success),
        "due_at": format_time(due_at),
        "elapsed_seconds": int((current_time - last_success).total_seconds()),
        "network_accessed": False,
    }


@contextlib.contextmanager
def exclusive_lock(state_file: Path) -> Iterator[None]:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file = state_file.with_suffix(f"{state_file.suffix}.lock")
    with lock_file.open("a+b") as lock:
        if os.name == "nt":
            # 空ファイルの範囲ロックは行わない。Windowsで1バイトのロック対象を
            # 常に確保し、同時確認による状態と候補の二重更新を防ぐため。
            lock.seek(0, os.SEEK_END)
            if lock.tell() == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def ensure_allowed_url(url: str, allowed_hosts: set[str]) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        raise UpstreamError(f"許可されていない取得先です: {url}")


def run_ax_json(arguments: list[str]) -> Any:
    executable = shutil.which("ax")
    if executable is None:
        raise UpstreamError("axコマンドが見つかりません")
    completed = subprocess.run(
        [executable, *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise UpstreamError(f"axによる取得に失敗しました: {detail}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise UpstreamError(f"axのJSON出力を解析できません: {error}") from error


def find_current_archive(contract: dict[str, Any], allowed_hosts: set[str]) -> str:
    resource = contract["sources"]["resources_page"]
    ensure_allowed_url(resource["url"], allowed_hosts)
    rows = run_ax_json(
        [
            resource["url"],
            resource["markdown_link_selector"],
            "--row",
            "href=@href",
            "--json",
            "--fresh",
        ]
    )
    if not isinstance(rows, list) or len(rows) != 1 or not rows[0].get("href"):
        raise UpstreamError(f"Markdown ZIPのリンクを一意に取得できません: {rows!r}")
    archive_url = urljoin(resource["url"], rows[0]["href"])
    ensure_allowed_url(archive_url, allowed_hosts)
    return archive_url


def read_source_validator(url: str, allowed_hosts: set[str]) -> dict[str, Any]:
    ensure_allowed_url(url, allowed_hosts)
    response = run_ax_json([url, "-I"])
    if not response.get("ok"):
        raise UpstreamError(f"公式ソースを確認できません: {url}")
    final_url = response.get("url", url)
    ensure_allowed_url(final_url, allowed_hosts)
    headers = response.get("headers", {})
    return {
        "url": final_url,
        "etag": headers.get("etag"),
        "last_modified": headers.get("last-modified"),
    }


def download_archive(url: str, destination: Path, allowed_hosts: set[str]) -> None:
    ensure_allowed_url(url, allowed_hosts)
    executable = shutil.which("ax")
    if executable is None:
        raise UpstreamError("axコマンドが見つかりません")
    completed = subprocess.run(
        [
            executable,
            url,
            "-o",
            str(destination),
            "-f",
            "--max-bytes",
            "52428800",
            "-m",
            "60",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise UpstreamError(f"ZIPの取得に失敗しました: {detail}")
    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise UpstreamError(f"ZIP取得結果を解析できません: {error}") from error
    if not response.get("ok") or not destination.is_file():
        raise UpstreamError(f"ZIPが保存されませんでした: {url}")
    ensure_allowed_url(response.get("url", url), allowed_hosts)


def extract_archive(archive: Path, destination: Path) -> Path:
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            member_path = PurePosixPath(member.filename)
            file_type = (member.external_attr >> 16) & 0o170000
            if member_path.is_absolute() or ".." in member_path.parts:
                raise UpstreamError(f"ZIPに不正なパスがあります: {member.filename}")
            if file_type == 0o120000:
                raise UpstreamError(
                    f"ZIP内のシンボリックリンクは展開しません: {member.filename}"
                )
        bundle.extractall(destination)

    if (destination / "README.md").is_file() and (destination / "index.md").is_file():
        return destination
    candidates = sorted(
        path.parent
        for path in destination.rglob("README.md")
        if (path.parent / "index.md").is_file()
    )
    if len(candidates) != 1:
        raise UpstreamError(
            f"ZIP内のスナップショットルートを特定できません: {candidates}"
        )
    return candidates[0]


def index_by_path(index: dict[str, Any]) -> dict[str, str]:
    return {entry["path"]: entry["sha256"] for entry in index["files"]}


def diff_indexes(base: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    old = index_by_path(base)
    new = index_by_path(candidate)
    added = sorted(new.keys() - old.keys())
    deleted = sorted(old.keys() - new.keys())
    changed = sorted(path for path in new.keys() & old.keys() if new[path] != old[path])
    return {
        "counts": {
            "added": len(added),
            "changed": len(changed),
            "deleted": len(deleted),
        },
        "added": added,
        "changed": changed,
        "deleted": deleted,
    }


def snapshot_id_from_url(archive_url: str, tree_sha256: str) -> str:
    match = re.search(r"dads-markdown-(\d{4})(\d{2})(\d{2})\.zip$", archive_url)
    if match:
        return "-".join(match.groups())
    return f"snapshot-{tree_sha256[:12]}"


def write_candidate(
    candidate_root: Path,
    extracted_snapshot: Path,
    archive_file: Path,
    archive_url: str,
    base_manifest: dict[str, Any],
    candidate_index: dict[str, Any],
    checked_at: dt.datetime,
) -> tuple[str, str, dict[str, Any]]:
    archive_sha256 = sha256_file(archive_file)
    snapshot_id = snapshot_id_from_url(archive_url, candidate_index["tree_sha256"])
    candidate_id = f"{snapshot_id}-{archive_sha256[:12]}"
    if not CANDIDATE_ID_PATTERN.fullmatch(candidate_id):
        raise UpstreamError(f"候補IDを安全に生成できません: {candidate_id}")

    manifest_dir = base_manifest["_manifest_dir"]
    active_index_path = manifest_dir / base_manifest["active_snapshot"]["index_path"]
    base_index = load_object(active_index_path)
    difference = diff_indexes(base_index, candidate_index)

    candidate_root.mkdir(parents=True, exist_ok=True)
    destination = candidate_root / candidate_id
    if destination.exists():
        existing_manifest = load_object(destination / "candidate-manifest.json")
        if (
            existing_manifest.get("candidate_snapshot", {})
            .get("archive", {})
            .get("sha256")
            != archive_sha256
        ):
            raise UpstreamError(f"同じ候補IDに異なる内容があります: {candidate_id}")
        return candidate_id, "candidate_exists", difference

    staging = Path(tempfile.mkdtemp(prefix=f".{candidate_id}.", dir=candidate_root))
    try:
        shutil.copytree(extracted_snapshot, staging / "snapshot")
        shutil.copy2(archive_file, staging / "archive.zip")
        atomic_write_json(staging / "source-index.json", candidate_index)
        candidate_index_sha256 = sha256_file(staging / "source-index.json")
        candidate_manifest = {
            "schema_version": 1,
            "candidate_id": candidate_id,
            "base_snapshot_id": base_manifest["active_snapshot"]["id"],
            "candidate_snapshot": {
                "id": snapshot_id,
                "dads_version": candidate_index["dads_version"],
                "index_sha256": candidate_index_sha256,
                "archive": {
                    "url": archive_url,
                    "sha256": archive_sha256,
                    "downloaded_at": format_time(checked_at),
                },
                "corpus": {
                    "markdown_count": candidate_index["markdown_count"],
                    "official_document_count": candidate_index[
                        "official_document_count"
                    ],
                    "auxiliary_document_count": candidate_index[
                        "auxiliary_document_count"
                    ],
                    "tree_sha256": candidate_index["tree_sha256"],
                },
            },
        }
        atomic_write_json(staging / "candidate-manifest.json", candidate_manifest)
        atomic_write_json(staging / "diff-summary.json", difference)
        os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return candidate_id, "candidate_created", difference


def source_validators(
    contract: dict[str, Any],
    archive_url: str,
    allowed_hosts: set[str],
) -> dict[str, Any]:
    validators: dict[str, Any] = {
        "archive_url": archive_url,
        "archive": read_source_validator(archive_url, allowed_hosts),
    }
    for name, source in contract["sources"].items():
        validators[name] = read_source_validator(source["url"], allowed_hosts)
    return validators


def mark_failed_attempt(
    state_file: Path, state: dict[str, Any], attempted_at: dt.datetime
) -> None:
    state["last_attempted_at"] = format_time(attempted_at)
    state["last_check_result"] = "failed"
    atomic_write_json(state_file, state)


def check_upstream(arguments: argparse.Namespace) -> dict[str, Any]:
    if not arguments.network_approved:
        raise UpstreamError("外部確認には--network-approvedが必要です")

    attempted_at = utc_now()
    with exclusive_lock(arguments.state_file):
        manifest = load_object(arguments.manifest_file)
        manifest["_manifest_dir"] = arguments.manifest_file.parent
        state = load_state_or_default(arguments.state_file, manifest)
        current_status = status_result(
            arguments.state_file, arguments.contract_file, attempted_at
        )
        if current_status["status"] == "fresh" and not arguments.force:
            return {
                "ok": True,
                "result": "skipped_fresh",
                "status": current_status,
            }

        contract = load_object(arguments.contract_file)
        allowed_hosts = set(contract["allowed_hosts"])
        try:
            archive_url = find_current_archive(contract, allowed_hosts)
            validators = source_validators(contract, archive_url, allowed_hosts)
            active_archive_url = manifest["active_snapshot"]["archive"]["url"]
            active_archive_sha256 = manifest["active_snapshot"]["archive"]["sha256"]
            result: dict[str, Any]

            with tempfile.TemporaryDirectory(prefix="dads-update-") as temporary:
                temporary_dir = Path(temporary)
                archive_file = temporary_dir / "candidate.zip"
                download_archive(archive_url, archive_file, allowed_hosts)
                archive_sha256 = sha256_file(archive_file)
                validators["archive"]["sha256"] = archive_sha256

                if (
                    archive_url == active_archive_url
                    and archive_sha256 == active_archive_sha256
                ):
                    result = {
                        "ok": True,
                        "result": "unchanged",
                        "archive_url": archive_url,
                        "archive_sha256": archive_sha256,
                    }
                else:
                    extracted_dir = temporary_dir / "extracted"
                    extracted_dir.mkdir()
                    snapshot_dir = extract_archive(archive_file, extracted_dir)
                    candidate_index = scan_snapshot(snapshot_dir)
                    candidate_id, candidate_result, difference = write_candidate(
                        candidate_root=arguments.candidate_root,
                        extracted_snapshot=snapshot_dir,
                        archive_file=archive_file,
                        archive_url=archive_url,
                        base_manifest=manifest,
                        candidate_index=candidate_index,
                        checked_at=attempted_at,
                    )
                    pending = list(state.get("pending_candidate_ids", []))
                    if candidate_id not in pending:
                        pending.append(candidate_id)
                    state["pending_candidate_ids"] = pending
                    result = {
                        "ok": True,
                        "result": candidate_result,
                        "candidate_id": candidate_id,
                        "archive_url": archive_url,
                        "archive_sha256": archive_sha256,
                        "diff": difference["counts"],
                    }

            completed_at = utc_now()
            state.update(
                {
                    "schema_version": 1,
                    "checked_contract_version": contract["contract_version"],
                    "last_attempted_at": format_time(attempted_at),
                    "last_successful_check_at": format_time(completed_at),
                    "last_check_result": (
                        "candidate_found"
                        if result["result"].startswith("candidate_")
                        else "unchanged"
                    ),
                    "source_validators": validators,
                    "active_snapshot_id": manifest["active_snapshot"]["id"],
                }
            )
            state.setdefault("pending_candidate_ids", [])
            atomic_write_json(arguments.state_file, state)
            result["checked_at"] = format_time(completed_at)
            return result
        # 更新確認中の例外はここで選別しない。部分成功を成功として残すことを防ぐため。
        except Exception as error:
            try:
                mark_failed_attempt(arguments.state_file, state, attempted_at)
            except Exception as state_error:  # noqa: BLE001
                raise UpstreamError(
                    f"更新確認に失敗し、失敗状態も保存できませんでした: {state_error}"
                ) from error
            raise


def promote_candidate(arguments: argparse.Namespace) -> dict[str, Any]:
    if not arguments.human_approved:
        raise UpstreamError("候補の昇格には--human-approvedが必要です")
    if not CANDIDATE_ID_PATTERN.fullmatch(arguments.candidate_id):
        raise UpstreamError(f"候補IDが不正です: {arguments.candidate_id}")

    with exclusive_lock(arguments.state_file):
        manifest = load_object(arguments.manifest_file)
        state = load_state_or_default(arguments.state_file, manifest)
        candidate_dir = arguments.candidate_root / arguments.candidate_id
        candidate_manifest = load_object(candidate_dir / "candidate-manifest.json")
        candidate_index_file = candidate_dir / "source-index.json"
        candidate_snapshot_dir = candidate_dir / "snapshot"
        candidate_archive_file = candidate_dir / "archive.zip"

        if candidate_manifest.get("candidate_id") != arguments.candidate_id:
            raise UpstreamError("候補マニフェストのIDが一致しません")
        if (
            candidate_manifest.get("base_snapshot_id")
            != manifest["active_snapshot"]["id"]
        ):
            raise UpstreamError("候補の基準版が現在の有効版と一致しません")

        snapshot = candidate_manifest["candidate_snapshot"]
        if sha256_file(candidate_index_file) != snapshot["index_sha256"]:
            raise UpstreamError("候補の索引ハッシュが一致しません")
        if sha256_file(candidate_archive_file) != snapshot["archive"]["sha256"]:
            raise UpstreamError("候補のZIPハッシュが一致しません")

        verification = verify_snapshot(candidate_snapshot_dir, candidate_index_file)
        if not verification["ok"]:
            raise UpstreamError(
                f"候補スナップショットの検証に失敗しました: {verification['errors']}"
            )

        destination_id = snapshot["id"]
        destination = arguments.upstream_root / destination_id
        if destination.exists():
            existing = scan_snapshot(destination)
            if existing["tree_sha256"] != snapshot["corpus"]["tree_sha256"]:
                destination_id = (
                    f"{destination_id}-{snapshot['corpus']['tree_sha256'][:12]}"
                )
                destination = arguments.upstream_root / destination_id

        if not destination.exists():
            arguments.upstream_root.mkdir(parents=True, exist_ok=True)
            staging_root = Path(
                tempfile.mkdtemp(
                    prefix=f".{destination_id}.", dir=arguments.upstream_root
                )
            )
            staging_snapshot = staging_root / destination_id
            try:
                shutil.copytree(candidate_snapshot_dir, staging_snapshot)
                shutil.copy2(
                    candidate_index_file, staging_snapshot / "source-index.json"
                )
                os.replace(staging_snapshot, destination)
            finally:
                if staging_root.exists():
                    shutil.rmtree(staging_root)

        previous_id = manifest["active_snapshot"]["id"]
        new_active = {
            "id": destination_id,
            "path": f"upstream/{destination_id}",
            "index_path": f"upstream/{destination_id}/source-index.json",
            "index_sha256": snapshot["index_sha256"],
            "dads_version": snapshot["dads_version"],
            "archive": snapshot["archive"],
            "corpus": snapshot["corpus"],
        }
        manifest.update(
            {
                "schema_version": 1,
                "previous_snapshot_id": previous_id,
                "active_snapshot": new_active,
            }
        )
        atomic_write_json(arguments.manifest_file, manifest)

        state["active_snapshot_id"] = destination_id
        state["pending_candidate_ids"] = [
            value
            for value in state.get("pending_candidate_ids", [])
            if value != arguments.candidate_id
        ]
        atomic_write_json(arguments.state_file, state)
        return {
            "ok": True,
            "result": "promoted",
            "candidate_id": arguments.candidate_id,
            "active_snapshot_id": destination_id,
            "previous_snapshot_id": previous_id,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    state_file = default_state_file()
    references = SKILL_ROOT / "references"

    status_parser = subparsers.add_parser(
        "status", help="ローカル状態だけで30日判定する"
    )
    status_parser.add_argument("--state-file", type=Path, default=state_file)
    status_parser.add_argument(
        "--contract-file", type=Path, default=references / "update-contract.json"
    )

    check_parser = subparsers.add_parser("check", help="同意後に公式ソースを確認する")
    check_parser.add_argument("--network-approved", action="store_true")
    check_parser.add_argument("--force", action="store_true")
    check_parser.add_argument("--state-file", type=Path, default=state_file)
    check_parser.add_argument(
        "--contract-file", type=Path, default=references / "update-contract.json"
    )
    check_parser.add_argument(
        "--manifest-file", type=Path, default=references / "source-manifest.json"
    )
    check_parser.add_argument(
        "--candidate-root", type=Path, default=state_file.parent / "candidates"
    )

    promote_parser = subparsers.add_parser("promote", help="承認済み候補を有効化する")
    promote_parser.add_argument("--candidate-id", required=True)
    promote_parser.add_argument("--human-approved", action="store_true")
    promote_parser.add_argument("--state-file", type=Path, default=state_file)
    promote_parser.add_argument(
        "--manifest-file", type=Path, default=references / "source-manifest.json"
    )
    promote_parser.add_argument(
        "--candidate-root", type=Path, default=state_file.parent / "candidates"
    )
    promote_parser.add_argument(
        "--upstream-root", type=Path, default=references / "upstream"
    )
    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()
    for attribute in (
        "state_file",
        "contract_file",
        "manifest_file",
        "candidate_root",
        "upstream_root",
    ):
        if hasattr(arguments, attribute):
            setattr(arguments, attribute, getattr(arguments, attribute).resolve())

    try:
        if arguments.command == "status":
            result = status_result(arguments.state_file, arguments.contract_file)
        elif arguments.command == "check":
            result = check_upstream(arguments)
        else:
            result = promote_candidate(arguments)
    except (
        OSError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        SnapshotError,
        UpstreamError,
        zipfile.BadZipFile,
    ) as error:
        result = {"ok": False, "error": str(error)}

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
