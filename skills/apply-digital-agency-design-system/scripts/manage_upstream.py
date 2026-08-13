#!/usr/bin/env python3
"""Manage DADS update freshness, candidate retrieval, and approved promotion."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from build_index import SnapshotError, atomic_write_json, scan_snapshot, sha256_file
from skill_lock import exclusive_file_lock
from upstream_fetch import (
    MAX_ARCHIVE_BYTES,
    UpstreamError,
    build_source_policy,
    ensure_allowed_url,
    select_fetch_backend,
)
from verify_snapshot import verify_snapshot

UTC = dt.timezone.utc
RFC3339_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
CANDIDATE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
SNAPSHOT_ID_PATTERN = re.compile(
    r"^(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|snapshot-[0-9a-f]{12})$"
)
SKILL_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR_ENV = "DADS_SKILL_STATE_DIR"
MAX_EXTRACTED_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10_000
WINDOWS_RESERVED_NAME_PATTERN = re.compile(
    r"^(?:con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\.|$)",
    re.IGNORECASE,
)
WINDOWS_INVALID_PATH_CHARACTERS = frozenset('<>:"|?*')


class ManualDownloadRequired(UpstreamError):
    """Report a safe manual recovery path after an archive transfer fails."""

    def __init__(
        self,
        error: Exception,
        archive_url: str,
        resources_page_url: str,
    ) -> None:
        super().__init__(f"ZIPの自動取得に失敗しました: {error}")
        self.recovery = {
            "kind": "manual_archive_download",
            "archive_url": archive_url,
            "resources_page_url": resources_page_url,
            "next_command": "import-archive",
        }
        self.result = {
            "ok": False,
            "result": "manual_download_available",
            "error_code": "archive_download_failed",
            "error": str(self),
            "manual_download": self.recovery,
            "recovery": self.recovery,
        }

    def as_result(self) -> dict[str, Any]:
        return self.result


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
        state = load_object(state_file)
        state.pop("source_validators", None)
        state.setdefault("source_verification", {})
        state.setdefault("pending_manual_download", None)
        return state
    return {
        "schema_version": 1,
        "checked_contract_version": None,
        "last_attempted_at": None,
        "last_successful_check_at": None,
        "last_check_result": None,
        "source_verification": {},
        "active_snapshot_id": manifest["active_snapshot"]["id"],
        "pending_candidate_ids": [],
        "pending_manual_download": None,
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


def exclusive_lock(state_file: Path):
    lock_file = state_file.with_suffix(f"{state_file.suffix}.lock")
    return exclusive_file_lock(lock_file)


def skill_update_lock_file(arguments: argparse.Namespace) -> Path:
    configured = getattr(arguments, "skill_lock_file", None)
    if configured is not None:
        return configured
    # Direct function callers may provide a standalone test or alternate manifest.
    # Keep that lock beside their writable state instead of guessing a Skill root.
    return arguments.state_file.with_suffix(
        f"{arguments.state_file.suffix}.skill-update.lock"
    )


def extract_archive(archive: Path, destination: Path) -> Path:
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > MAX_ARCHIVE_ENTRIES:
            raise UpstreamError(f"ZIPのエントリ数が上限を超えています: {len(members)}")

        seen_paths: set[str] = set()
        file_paths: set[str] = set()
        extracted_bytes = 0
        for member in members:
            member_path = PurePosixPath(member.filename)
            file_type = (member.external_attr >> 16) & 0o170000
            canonical_path = member_path.as_posix().rstrip("/")
            path_segments = member_path.parts
            if (
                not canonical_path
                or member_path.is_absolute()
                or ".." in member_path.parts
                or "." in member_path.parts
                or "\\" in member.filename
                or any(
                    not segment
                    or segment.endswith((" ", "."))
                    or any(ord(character) < 32 for character in segment)
                    or any(
                        character in WINDOWS_INVALID_PATH_CHARACTERS
                        for character in segment
                    )
                    or WINDOWS_RESERVED_NAME_PATTERN.match(segment)
                    for segment in path_segments
                )
            ):
                raise UpstreamError(f"ZIPに不正なパスがあります: {member.filename}")
            comparable_path = unicodedata.normalize("NFC", canonical_path).casefold()
            if comparable_path in seen_paths:
                raise UpstreamError(f"ZIPに重複したパスがあります: {member.filename}")
            comparable_parents = {
                unicodedata.normalize("NFC", parent.as_posix()).casefold()
                for parent in member_path.parents
                if parent.as_posix() != "."
            }
            if comparable_parents & file_paths or (
                member.is_dir()
                and any(path.startswith(f"{comparable_path}/") for path in file_paths)
            ):
                raise UpstreamError(
                    f"ZIPにファイルとディレクトリの衝突があります: {member.filename}"
                )
            seen_paths.add(comparable_path)
            if not member.is_dir():
                file_paths.add(comparable_path)

            if member.flag_bits & 0x1:
                raise UpstreamError(
                    f"ZIP内の暗号化されたファイルは展開しません: {member.filename}"
                )
            if file_type not in (0, 0o040000, 0o100000):
                raise UpstreamError(
                    f"ZIP内の特殊ファイルは展開しません: {member.filename}"
                )
            extracted_bytes += member.file_size
            if extracted_bytes > MAX_EXTRACTED_BYTES:
                raise UpstreamError(
                    "ZIP展開後の合計サイズが上限を超えています: "
                    f"{extracted_bytes} > {MAX_EXTRACTED_BYTES}"
                )
        actual_extracted_bytes = 0
        for member in members:
            member_path = PurePosixPath(member.filename)
            target = destination.joinpath(*member_path.parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(member, "r") as source, target.open("xb") as output:
                while chunk := source.read(1024 * 1024):
                    actual_extracted_bytes += len(chunk)
                    if actual_extracted_bytes > MAX_EXTRACTED_BYTES:
                        raise UpstreamError(
                            "ZIP展開中の合計サイズが上限を超えました: "
                            f"{actual_extracted_bytes} > {MAX_EXTRACTED_BYTES}"
                        )
                    output.write(chunk)

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
    snapshot_root = candidates[0]
    outside_files = sorted(
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file() and not path.is_relative_to(snapshot_root)
    )
    if outside_files:
        raise UpstreamError(
            "ZIPのスナップショット外にファイルがあります: " + ", ".join(outside_files)
        )
    return snapshot_root


def reject_untracked_snapshot_files(snapshot_dir: Path) -> None:
    """Keep every promoted payload inside the Markdown-only snapshot index."""

    untracked = sorted(
        path.relative_to(snapshot_dir).as_posix()
        for path in snapshot_dir.rglob("*")
        if path.is_file() and path.suffix.casefold() != ".md"
    )
    if untracked:
        raise UpstreamError(
            "ZIPに索引対象外のファイルがあります: " + ", ".join(untracked)
        )


def assert_index_metadata(index: dict[str, Any]) -> None:
    if index.get("dads_version") is None or index.get("official_document_count", 0) < 1:
        raise UpstreamError("ZIPにバージョン付きのDADS Markdown文書がありません")


def verify_existing_candidate_archive(
    candidate_dir: Path,
    expected_index: dict[str, Any],
) -> None:
    """Rebuild an existing candidate from its ZIP before trusting its idempotency."""

    with tempfile.TemporaryDirectory(prefix="dads-candidate-verify-") as temporary:
        extracted_dir = Path(temporary) / "extracted"
        extracted_dir.mkdir()
        snapshot_dir = extract_archive(candidate_dir / "archive.zip", extracted_dir)
        reject_untracked_snapshot_files(snapshot_dir)
        if scan_snapshot(snapshot_dir) != expected_index:
            raise UpstreamError("既存候補のZIP内容が索引と一致しません")


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


def promoted_archive_metadata(candidate_archive: dict[str, Any]) -> dict[str, Any]:
    """Keep stable source-manifest fields while retaining acquisition provenance."""

    metadata = {
        "published_on": snapshot_id_from_url(candidate_archive["url"], "") or None,
        "url": candidate_archive["url"],
        "sha256": candidate_archive["sha256"],
        "verified_on": candidate_archive["acquired_at"][:10],
        "acquisition_method": candidate_archive["acquisition_method"],
        "source_url": candidate_archive["source_url"],
    }
    return metadata


def write_candidate(
    candidate_root: Path,
    extracted_snapshot: Path,
    archive_file: Path,
    archive_url: str,
    base_manifest: dict[str, Any],
    candidate_index: dict[str, Any],
    checked_at: dt.datetime,
    acquisition_method: str = "automatic",
    source_url: str | None = None,
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
        existing_manifest_file = destination / "candidate-manifest.json"
        existing_index_file = destination / "source-index.json"
        existing_archive_file = destination / "archive.zip"
        existing_snapshot_dir = destination / "snapshot"
        existing_manifest = load_object(existing_manifest_file)
        existing_snapshot = existing_manifest.get("candidate_snapshot", {})
        existing_archive = existing_snapshot.get("archive", {})
        legacy_candidate = (
            "downloaded_at" in existing_archive
            and "acquired_at" not in existing_archive
            and "acquisition_method" not in existing_archive
            and "source_url" not in existing_archive
        )
        acquired_at = existing_archive.get(
            "acquired_at", existing_archive.get("downloaded_at")
        )
        existing_source_url = existing_archive.get("source_url", archive_url)
        existing_acquisition_method = existing_archive.get(
            "acquisition_method", "automatic"
        )
        expected_corpus = {
            "markdown_count": candidate_index["markdown_count"],
            "official_document_count": candidate_index["official_document_count"],
            "auxiliary_document_count": candidate_index["auxiliary_document_count"],
            "tree_sha256": candidate_index["tree_sha256"],
        }
        snapshot_verification = verify_snapshot(
            existing_snapshot_dir,
            existing_index_file,
        )
        candidate_checks = {
            "candidate_id": existing_manifest.get("candidate_id") == candidate_id,
            "base_snapshot_id": existing_manifest.get("base_snapshot_id")
            == base_manifest["active_snapshot"]["id"],
            "snapshot_id": existing_snapshot.get("id") == snapshot_id,
            "archive_url": existing_archive.get("url") == archive_url,
            "archive_sha256": existing_archive.get("sha256") == archive_sha256,
            "source_url": existing_source_url == archive_url,
            "acquisition_method": existing_acquisition_method
            in {"automatic", "manual_download"},
            "acquired_at": isinstance(acquired_at, str),
            "dads_version": existing_snapshot.get("dads_version")
            == candidate_index["dads_version"],
            "archive_file": sha256_file(existing_archive_file) == archive_sha256,
            "index_sha256": sha256_file(existing_index_file)
            == existing_snapshot.get("index_sha256"),
            "index": load_object(existing_index_file) == candidate_index,
            "corpus": existing_snapshot.get("corpus") == expected_corpus,
            # Legacy candidates were created before promotion required the eight
            # foundation routes. Their exact index and archive are still checked
            # below, so they can be migrated without weakening integrity.
            "snapshot": snapshot_verification["ok"] or legacy_candidate,
            "diff": load_object(destination / "diff-summary.json") == difference,
        }
        candidate_mismatch = not all(candidate_checks.values())
        if candidate_mismatch:
            failed_checks = sorted(
                name for name, passed in candidate_checks.items() if not passed
            )
            raise UpstreamError(
                f"同じ候補IDに異なる内容があります: {candidate_id}: {failed_checks}"
            )
        parse_time(acquired_at)
        verify_existing_candidate_archive(destination, candidate_index)
        if legacy_candidate:
            migrated_manifest = dict(existing_manifest)
            migrated_snapshot = dict(existing_snapshot)
            migrated_snapshot["archive"] = {
                "url": archive_url,
                "sha256": archive_sha256,
                "acquired_at": acquired_at,
                "acquisition_method": "automatic",
                "source_url": archive_url,
            }
            migrated_manifest["candidate_snapshot"] = migrated_snapshot
            atomic_write_json(existing_manifest_file, migrated_manifest)
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
                    "acquired_at": format_time(checked_at),
                    "acquisition_method": acquisition_method,
                    "source_url": source_url or archive_url,
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


def evaluate_archive(
    *,
    archive_file: Path,
    archive_url: str,
    temporary_dir: Path,
    manifest: dict[str, Any],
    state: dict[str, Any],
    candidate_root: Path,
    checked_at: dt.datetime,
    acquisition_method: str,
) -> dict[str, Any]:
    """Validate one acquired ZIP and either compare or stage it as a candidate."""

    archive_sha256 = sha256_file(archive_file)
    active_archive = manifest["active_snapshot"]["archive"]
    is_active_archive = (
        archive_url == active_archive["url"]
        and archive_sha256 == active_archive["sha256"]
    )
    if is_active_archive and acquisition_method != "manual_download":
        return {
            "ok": True,
            "result": "unchanged",
            "archive_url": archive_url,
            "archive_sha256": archive_sha256,
            "acquisition_method": acquisition_method,
        }

    extracted_dir = temporary_dir / "extracted"
    extracted_dir.mkdir()
    snapshot_dir = extract_archive(archive_file, extracted_dir)
    reject_untracked_snapshot_files(snapshot_dir)
    candidate_index = scan_snapshot(snapshot_dir)
    if acquisition_method == "manual_download":
        assert_index_metadata(candidate_index)
    if is_active_archive:
        active_index_path = (
            manifest["_manifest_dir"] / manifest["active_snapshot"]["index_path"]
        )
        if candidate_index != load_object(active_index_path):
            raise UpstreamError("手動ZIPの内容が有効スナップショットと一致しません")
        return {
            "ok": True,
            "result": "unchanged",
            "archive_url": archive_url,
            "archive_sha256": archive_sha256,
            "acquisition_method": acquisition_method,
        }
    candidate_id, candidate_result, difference = write_candidate(
        candidate_root=candidate_root,
        extracted_snapshot=snapshot_dir,
        archive_file=archive_file,
        archive_url=archive_url,
        base_manifest=manifest,
        candidate_index=candidate_index,
        checked_at=checked_at,
        acquisition_method=acquisition_method,
        source_url=archive_url,
    )
    pending = list(state.get("pending_candidate_ids", []))
    if candidate_id not in pending:
        pending.append(candidate_id)
    state["pending_candidate_ids"] = pending
    return {
        "ok": True,
        "result": candidate_result,
        "candidate_id": candidate_id,
        "archive_url": archive_url,
        "archive_sha256": archive_sha256,
        "diff": difference["counts"],
        "acquisition_method": acquisition_method,
    }


def copy_local_archive(source: Path, destination: Path) -> int:
    """Copy a user-selected archive without mutating it and enforce the byte cap."""

    if not source.is_absolute():
        raise UpstreamError("ZIPはファイル名を含む絶対パスで指定してください")
    if source.is_symlink():
        raise UpstreamError(f"シンボリックリンクのZIPは取り込みません: {source}")
    resolved_source = source.resolve(strict=True)
    if not resolved_source.is_file():
        raise UpstreamError(f"ZIPが通常ファイルではありません: {source}")

    copied_bytes = 0
    try:
        with resolved_source.open("rb") as input_file, destination.open("xb") as output:
            while chunk := input_file.read(1024 * 1024):
                copied_bytes += len(chunk)
                if copied_bytes > MAX_ARCHIVE_BYTES:
                    raise UpstreamError(
                        "ZIPが取込上限を超えています: "
                        f"{copied_bytes} > {MAX_ARCHIVE_BYTES}"
                    )
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    if not zipfile.is_zipfile(destination):
        destination.unlink(missing_ok=True)
        raise UpstreamError(f"ZIP形式ではありません: {source}")
    return copied_bytes


def validate_pending_manual_download(
    pending: Any,
    contract: dict[str, Any],
    now: dt.datetime,
) -> tuple[str, dt.datetime, str]:
    if not isinstance(pending, dict):
        raise UpstreamError(
            "手動取得待ちがありません。先に公式更新確認を実行してください"
        )
    if pending.get("contract_version") != contract.get("contract_version"):
        raise UpstreamError(
            "更新契約が変わったため、公式ZIPの確認からやり直してください"
        )
    archive_url = pending.get("archive_url")
    discovered_at_text = pending.get("discovered_at")
    fetch_backend = pending.get("fetch_backend")
    required_text_values = (archive_url, discovered_at_text, fetch_backend)
    if not all(isinstance(value, str) and value for value in required_text_values):
        raise UpstreamError("手動取得待ちの状態が不正です")

    ensure_allowed_url(
        archive_url,
        build_source_policy(contract),
        require_archive=True,
    )
    discovered_at = parse_time(discovered_at_text)
    if discovered_at > now:
        raise UpstreamError("公式ZIPの確認日時が未来です")
    freshness = dt.timedelta(days=int(contract["freshness_days"]))
    if now >= discovered_at + freshness:
        raise UpstreamError(
            "公式ZIPの確認から30日以上経過したため、公式確認からやり直してください"
        )
    return archive_url, discovered_at, fetch_backend


def mark_failed_attempt(
    state_file: Path,
    state: dict[str, Any],
    attempted_at: dt.datetime,
    result: str = "failed",
) -> None:
    state["last_attempted_at"] = format_time(attempted_at)
    state["last_check_result"] = result
    atomic_write_json(state_file, state)


def check_upstream(arguments: argparse.Namespace) -> dict[str, Any]:
    if not arguments.network_approved:
        raise UpstreamError("外部確認には--network-approvedが必要です")

    attempted_at = utc_now()
    with (
        exclusive_file_lock(skill_update_lock_file(arguments)),
        exclusive_lock(arguments.state_file),
    ):
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
        # A new check invalidates an older manual handoff unless this run discovers
        # and records the exact official archive URL again.
        state["pending_manual_download"] = None
        try:
            backend = select_fetch_backend(
                getattr(arguments, "fetch_backend", "auto"), contract
            )
            archive_url = backend.find_current_archive(contract)
            ensure_allowed_url(
                archive_url,
                build_source_policy(contract),
                require_archive=True,
            )
            discovered_at = utc_now()

            with tempfile.TemporaryDirectory(prefix="dads-update-") as temporary:
                temporary_dir = Path(temporary)
                archive_file = temporary_dir / "candidate.zip"
                try:
                    download_result = backend.download_archive(
                        archive_url, archive_file
                    )
                except Exception as error:
                    resources_page_url = contract["sources"]["resources_page"]["url"]
                    pending_manual_download = {
                        "archive_url": archive_url,
                        "discovered_at": format_time(discovered_at),
                        "contract_version": contract["contract_version"],
                        "fetch_backend": backend.name,
                    }
                    state["pending_manual_download"] = pending_manual_download
                    mark_failed_attempt(
                        arguments.state_file,
                        state,
                        attempted_at,
                        result="manual_download_pending",
                    )
                    raise ManualDownloadRequired(
                        error,
                        archive_url=archive_url,
                        resources_page_url=resources_page_url,
                    ) from error
                archive_url = download_result["url"]
                archive_sha256 = sha256_file(archive_file)
                source_verification = {
                    "fetch_backend": backend.name,
                    "acquisition_method": "automatic",
                    "archive": {
                        **download_result,
                        "sha256": archive_sha256,
                    },
                }
                result = evaluate_archive(
                    archive_file=archive_file,
                    archive_url=archive_url,
                    temporary_dir=temporary_dir,
                    manifest=manifest,
                    state=state,
                    candidate_root=arguments.candidate_root,
                    checked_at=attempted_at,
                    acquisition_method="automatic",
                )
                result["fetch_backend"] = backend.name

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
                    "source_verification": source_verification,
                    "active_snapshot_id": manifest["active_snapshot"]["id"],
                    "pending_manual_download": None,
                }
            )
            state.setdefault("pending_candidate_ids", [])
            atomic_write_json(arguments.state_file, state)
            result["checked_at"] = format_time(completed_at)
            return result
        except ManualDownloadRequired:
            raise
        # 更新確認中の例外はここで選別しない。部分成功を成功として残すことを防ぐため。
        except Exception as error:
            try:
                mark_failed_attempt(arguments.state_file, state, attempted_at)
            except Exception as state_error:  # noqa: BLE001
                raise UpstreamError(
                    f"更新確認に失敗し、失敗状態も保存できませんでした: {state_error}"
                ) from error
            raise


def import_archive(arguments: argparse.Namespace) -> dict[str, Any]:
    """Import a manually downloaded ZIP without performing network access."""

    attempted_at = utc_now()
    with (
        exclusive_file_lock(skill_update_lock_file(arguments)),
        exclusive_lock(arguments.state_file),
    ):
        manifest = load_object(arguments.manifest_file)
        manifest["_manifest_dir"] = arguments.manifest_file.parent
        state = load_state_or_default(arguments.state_file, manifest)
        contract = load_object(arguments.contract_file)
        try:
            archive_url, discovered_at, fetch_backend = (
                validate_pending_manual_download(
                    state.get("pending_manual_download"),
                    contract,
                    attempted_at,
                )
            )
            with tempfile.TemporaryDirectory(prefix="dads-manual-import-") as temporary:
                temporary_dir = Path(temporary)
                archive_file = temporary_dir / "manual.zip"
                archive_bytes = copy_local_archive(
                    arguments.archive_file,
                    archive_file,
                )
                result = evaluate_archive(
                    archive_file=archive_file,
                    archive_url=archive_url,
                    temporary_dir=temporary_dir,
                    manifest=manifest,
                    state=state,
                    candidate_root=arguments.candidate_root,
                    checked_at=attempted_at,
                    acquisition_method="manual_download",
                )

            completed_at = utc_now()
            state.update(
                {
                    "schema_version": 1,
                    "last_attempted_at": format_time(attempted_at),
                    # ローカルZIPの候補化は、完了した外部確認とは
                    # 別の事実として記録し、30日の鮮度は更新しない。
                    "last_check_result": (
                        "candidate_found"
                        if result["result"].startswith("candidate_")
                        else "manual_import_unchanged"
                    ),
                    "source_verification": {
                        "fetch_backend": fetch_backend,
                        "acquisition_method": "manual_download",
                        "archive": {
                            "url": archive_url,
                            "bytes": archive_bytes,
                            "sha256": result["archive_sha256"],
                        },
                    },
                    "active_snapshot_id": manifest["active_snapshot"]["id"],
                    "pending_manual_download": None,
                }
            )
            state.setdefault("pending_candidate_ids", [])
            atomic_write_json(arguments.state_file, state)
            result.update(
                {
                    "fetch_backend": fetch_backend,
                    "archive_discovered_at": format_time(discovered_at),
                    "imported_at": format_time(completed_at),
                    "network_accessed": False,
                }
            )
            return result
        except Exception as error:
            try:
                mark_failed_attempt(
                    arguments.state_file,
                    state,
                    attempted_at,
                    result="manual_import_failed",
                )
            except Exception as state_error:  # noqa: BLE001
                raise UpstreamError(
                    f"手動ZIPの取込に失敗し、失敗状態も保存できませんでした: {state_error}"
                ) from error
            raise


def promote_candidate(arguments: argparse.Namespace) -> dict[str, Any]:
    if not arguments.human_approved:
        raise UpstreamError("候補の昇格には--human-approvedが必要です")
    if not CANDIDATE_ID_PATTERN.fullmatch(arguments.candidate_id):
        raise UpstreamError(f"候補IDが不正です: {arguments.candidate_id}")

    with (
        exclusive_file_lock(skill_update_lock_file(arguments)),
        exclusive_lock(arguments.state_file),
    ):
        manifest = load_object(arguments.manifest_file)
        contract = load_object(arguments.contract_file)
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
        archive = snapshot["archive"]
        ensure_allowed_url(
            archive["url"],
            build_source_policy(contract),
            require_archive=True,
        )
        if sha256_file(candidate_index_file) != snapshot["index_sha256"]:
            raise UpstreamError("候補の索引ハッシュが一致しません")
        if sha256_file(candidate_archive_file) != archive["sha256"]:
            raise UpstreamError("候補のZIPハッシュが一致しません")

        verification = verify_snapshot(candidate_snapshot_dir, candidate_index_file)
        if not verification["ok"]:
            raise UpstreamError(
                f"候補スナップショットの検証に失敗しました: {verification['errors']}"
            )

        expected_index = load_object(candidate_index_file)
        with tempfile.TemporaryDirectory(prefix="dads-promote-verify-") as temporary:
            extracted_dir = Path(temporary) / "extracted"
            extracted_dir.mkdir()
            archive_snapshot_dir = extract_archive(
                candidate_archive_file,
                extracted_dir,
            )
            reject_untracked_snapshot_files(archive_snapshot_dir)
            archive_index = scan_snapshot(archive_snapshot_dir)
            if archive_index != expected_index:
                raise UpstreamError("候補のZIP内容が索引と一致しません")
            expected_snapshot_id = snapshot_id_from_url(
                archive["url"],
                archive_index["tree_sha256"],
            )
            destination_id = snapshot["id"]
            if (
                destination_id != expected_snapshot_id
                or SNAPSHOT_ID_PATTERN.fullmatch(destination_id) is None
            ):
                raise UpstreamError("候補のスナップショットIDが不正です")
            expected_candidate_id = f"{destination_id}-{archive['sha256'][:12]}"
            if arguments.candidate_id != expected_candidate_id:
                raise UpstreamError("候補IDがZIPとスナップショットに一致しません")

            destination = arguments.upstream_root / destination_id
            if destination.exists():
                existing = scan_snapshot(destination)
                if existing["tree_sha256"] != archive_index["tree_sha256"]:
                    destination_id = (
                        f"{destination_id}-{archive_index['tree_sha256'][:12]}"
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
                    # Promote from the immutable ZIP evidence, not from the mutable
                    # review copy stored next to the candidate manifest.
                    shutil.copytree(archive_snapshot_dir, staging_snapshot)
                    shutil.copy2(
                        candidate_index_file,
                        staging_snapshot / "source-index.json",
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
            "archive": promoted_archive_metadata(snapshot["archive"]),
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
    check_parser.add_argument(
        "--fetch-backend",
        choices=("auto", "ax", "stdlib"),
        default="auto",
        help="取得バックエンド。autoはaxを優先し、見つからなければ標準ライブラリを使う",
    )
    check_parser.add_argument("--state-file", type=Path, default=state_file)
    check_parser.add_argument(
        "--skill-lock-file",
        type=Path,
        default=SKILL_ROOT.parent / f".{SKILL_ROOT.name}.update.lock",
        help=argparse.SUPPRESS,
    )
    check_parser.add_argument(
        "--contract-file", type=Path, default=references / "update-contract.json"
    )
    check_parser.add_argument(
        "--manifest-file", type=Path, default=references / "source-manifest.json"
    )
    check_parser.add_argument(
        "--candidate-root", type=Path, default=state_file.parent / "candidates"
    )

    import_parser = subparsers.add_parser(
        "import-archive",
        help="手動取得した公式ZIPをネットワークなしで候補化する",
    )
    import_parser.add_argument("--archive-file", type=Path, required=True)
    import_parser.add_argument("--state-file", type=Path, default=state_file)
    import_parser.add_argument(
        "--skill-lock-file",
        type=Path,
        default=SKILL_ROOT.parent / f".{SKILL_ROOT.name}.update.lock",
        help=argparse.SUPPRESS,
    )
    import_parser.add_argument(
        "--contract-file", type=Path, default=references / "update-contract.json"
    )
    import_parser.add_argument(
        "--manifest-file", type=Path, default=references / "source-manifest.json"
    )
    import_parser.add_argument(
        "--candidate-root", type=Path, default=state_file.parent / "candidates"
    )

    promote_parser = subparsers.add_parser("promote", help="承認済み候補を有効化する")
    promote_parser.add_argument("--candidate-id", required=True)
    promote_parser.add_argument("--human-approved", action="store_true")
    promote_parser.add_argument("--state-file", type=Path, default=state_file)
    promote_parser.add_argument(
        "--skill-lock-file",
        type=Path,
        default=SKILL_ROOT.parent / f".{SKILL_ROOT.name}.update.lock",
        help=argparse.SUPPRESS,
    )
    promote_parser.add_argument(
        "--contract-file", type=Path, default=references / "update-contract.json"
    )
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
        "skill_lock_file",
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
        elif arguments.command == "import-archive":
            result = import_archive(arguments)
        else:
            result = promote_candidate(arguments)
    except ManualDownloadRequired as error:
        result = error.as_result()
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
