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
import ssl
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)

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
NETWORK_TIMEOUT_SECONDS = 60
MAX_PAGE_BYTES = 5 * 1024 * 1024
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_EXTRACTED_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10_000
HTTP_USER_AGENT = (
    "apply-digital-agency-design-system update-check "
    "(+https://github.com/Hideki-Kobayashi/apply-digital-agency-design-system)"
)
WINDOWS_RESERVED_NAME_PATTERN = re.compile(
    r"^(?:con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\.|$)",
    re.IGNORECASE,
)
WINDOWS_INVALID_PATH_CHARACTERS = frozenset('<>:"|?*')


class UpstreamError(RuntimeError):
    """Raised when an update operation cannot complete safely."""


@dataclass(frozen=True)
class SourcePolicy:
    allowed_hosts: frozenset[str]
    allowed_path_prefixes: tuple[str, ...]
    archive_path_pattern: re.Pattern[str]
    archive_content_types: frozenset[str]


class AnchorHrefParser(HTMLParser):
    """Collect anchor href values without requiring an HTML dependency."""

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(
        self, tag: str, attributes: list[tuple[str, str | None]]
    ) -> None:
        if tag.casefold() != "a":
            return
        for name, value in attributes:
            if name.casefold() == "href" and value:
                self.hrefs.append(value)
                return


class AllowedRedirectHandler(HTTPRedirectHandler):
    """Reject redirects that leave the official source policy."""

    max_redirections = 5

    def __init__(self, policy: SourcePolicy, require_archive: bool) -> None:
        super().__init__()
        self.policy = policy
        self.require_archive = require_archive

    def redirect_request(
        self,
        request: Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> Request | None:
        ensure_allowed_url(new_url, self.policy, self.require_archive)
        redirected = super().redirect_request(
            request, file_pointer, code, message, headers, new_url
        )
        if redirected is None or request.get_method() != "HEAD":
            return redirected
        return Request(
            new_url,
            headers=dict(request.header_items()),
            method="HEAD",
        )


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


def source_policy(contract: dict[str, Any]) -> SourcePolicy:
    try:
        return SourcePolicy(
            allowed_hosts=frozenset(contract["allowed_hosts"]),
            allowed_path_prefixes=tuple(contract["allowed_path_prefixes"]),
            archive_path_pattern=re.compile(contract["archive_path_pattern"]),
            archive_content_types=frozenset(contract["archive_content_types"]),
        )
    except (KeyError, TypeError, re.error) as error:
        raise UpstreamError(f"更新契約のURL方針を解析できません: {error}") from error


def ensure_allowed_url(
    url: str,
    policy: SourcePolicy,
    require_archive: bool = False,
) -> None:
    if any(ord(character) < 32 or ord(character) == 127 for character in url):
        raise UpstreamError("取得先URLに制御文字があります")
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError as error:
        raise UpstreamError(f"取得先URLを解析できません: {url}") from error

    path_allowed = any(
        parsed.path.startswith(prefix) for prefix in policy.allowed_path_prefixes
    )
    archive_allowed = (
        not require_archive
        or policy.archive_path_pattern.fullmatch(parsed.path) is not None
    )
    if (
        parsed.scheme != "https"
        or parsed.hostname not in policy.allowed_hosts
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or not path_allowed
        or not archive_allowed
        or bool(parsed.query)
        or bool(parsed.fragment)
    ):
        raise UpstreamError(f"許可されていない取得先です: {url}")


def resolve_link_parser(requested: str) -> str:
    if requested == "auto":
        return "ax" if shutil.which("ax") else "stdlib"
    if requested == "ax":
        if shutil.which("ax") is None:
            raise UpstreamError(
                "axコマンドが見つかりません。"
                "--link-parser stdlibを使うか、axをインストールしてください"
            )
        return "ax"
    if requested == "stdlib":
        return "stdlib"
    raise UpstreamError(f"未対応のリンク抽出方式です: {requested}")


def run_ax_json(arguments: list[str], input_text: str) -> Any:
    executable = shutil.which("ax")
    if executable is None:
        raise UpstreamError("axコマンドが見つかりません")
    try:
        completed = subprocess.run(
            [executable, *arguments],
            check=False,
            capture_output=True,
            input=input_text,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=NETWORK_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise UpstreamError("axによるリンク抽出が時間内に完了しませんでした") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise UpstreamError(f"axによるリンク抽出に失敗しました: {detail}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise UpstreamError(f"axのJSON出力を解析できません: {error}") from error


@contextlib.contextmanager
def open_source_response(
    url: str,
    policy: SourcePolicy,
    method: str = "GET",
    require_archive: bool = False,
    allowed_content_types: frozenset[str] | None = None,
) -> Iterator[Any]:
    ensure_allowed_url(url, policy, require_archive)
    request = Request(
        url,
        headers={
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "User-Agent": HTTP_USER_AGENT,
        },
        method=method,
    )
    tls_context = ssl.create_default_context()
    tls_context.minimum_version = ssl.TLSVersion.TLSv1_2
    opener = build_opener(
        # 環境プロキシを暗黙利用すると取得経路が端末ごとに変わるため無効にする。
        ProxyHandler({}),
        HTTPSHandler(context=tls_context),
        AllowedRedirectHandler(policy, require_archive),
    )
    try:
        response = opener.open(request, timeout=NETWORK_TIMEOUT_SECONDS)
    except (HTTPError, URLError, TimeoutError) as error:
        raise UpstreamError(
            f"公式ソースの取得に失敗しました: {url}: {error}"
        ) from error

    try:
        final_url = response.geturl()
        ensure_allowed_url(final_url, policy, require_archive)
        status = getattr(response, "status", None)
        if status != 200:
            raise UpstreamError(
                f"公式ソースが成功応答を返しませんでした: {final_url}: HTTP {status}"
            )
        content_encoding = response.headers.get("Content-Encoding")
        if content_encoding and content_encoding.casefold() != "identity":
            raise UpstreamError(
                f"圧縮されたHTTP応答は受け付けません: {content_encoding}"
            )
        content_type = response.headers.get_content_type().casefold()
        if allowed_content_types and content_type not in allowed_content_types:
            raise UpstreamError(f"Content-Typeが更新契約と一致しません: {content_type}")
        yield response
    finally:
        response.close()


def response_content_length(response: Any) -> int | None:
    value = response.headers.get("Content-Length")
    if value is None:
        return None
    try:
        length = int(value)
    except (TypeError, ValueError) as error:
        raise UpstreamError(f"Content-Lengthを解析できません: {value!r}") from error
    if length < 0:
        raise UpstreamError(f"Content-Lengthが負の値です: {length}")
    return length


def response_validator(response: Any) -> dict[str, Any]:
    return {
        "url": response.geturl(),
        "etag": response.headers.get("ETag"),
        "last_modified": response.headers.get("Last-Modified"),
        "content_type": response.headers.get_content_type().casefold(),
        "content_length": response_content_length(response),
    }


def read_bounded_response(response: Any, max_bytes: int) -> bytes:
    declared_length = response_content_length(response)
    if declared_length is not None and declared_length > max_bytes:
        raise UpstreamError(
            f"取得サイズが上限を超えています: {declared_length} > {max_bytes}"
        )

    chunks: list[bytes] = []
    total = 0
    while chunk := response.read(min(1024 * 1024, max_bytes + 1 - total)):
        total += len(chunk)
        if total > max_bytes:
            raise UpstreamError(f"取得サイズが上限を超えています: {max_bytes}")
        chunks.append(chunk)
    return b"".join(chunks)


def archive_urls_from_html(
    document: str,
    contains: str,
    ends_with: str,
    base_url: str,
    policy: SourcePolicy,
) -> list[str]:
    if not contains or not ends_with:
        raise UpstreamError("アーカイブのリンク条件が空です")

    parser = AnchorHrefParser()
    parser.feed(document)
    urls: list[str] = []
    for href in parser.hrefs:
        if contains not in href or not href.endswith(ends_with):
            continue
        archive_url = urljoin(base_url, href)
        ensure_allowed_url(archive_url, policy, require_archive=True)
        if archive_url not in urls:
            urls.append(archive_url)
    return urls


def archive_urls_with_ax(
    document: str,
    link_rule: dict[str, str],
    base_url: str,
    policy: SourcePolicy,
) -> list[str]:
    contains = link_rule["href_contains"]
    ends_with = link_rule["href_suffix"]
    if any(character in contains + ends_with for character in "'[]"):
        raise UpstreamError("ax用のリンク条件へ安全に変換できません")
    selector = f"a[href*='{contains}'][href$='{ends_with}']"
    rows = run_ax_json(
        [
            "-",
            selector,
            "--row",
            "href=@href",
            "--json",
            "--all",
            "--no-cache",
        ],
        input_text=document,
    )
    if not isinstance(rows, list):
        raise UpstreamError(f"Markdown ZIPのリンクを一意に取得できません: {rows!r}")
    urls: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("href"):
            raise UpstreamError(f"Markdown ZIPのリンクを解析できません: {row!r}")
        archive_url = urljoin(base_url, row["href"])
        ensure_allowed_url(archive_url, policy, require_archive=True)
        if archive_url not in urls:
            urls.append(archive_url)
    return urls


def find_current_archive(
    contract: dict[str, Any],
    policy: SourcePolicy,
    link_parser: str,
) -> tuple[str, dict[str, Any]]:
    resource = contract["sources"]["resources_page"]
    resource_url = resource["url"]
    with open_source_response(
        resource_url,
        policy,
        allowed_content_types=frozenset({"text/html"}),
    ) as response:
        document_bytes = read_bounded_response(response, MAX_PAGE_BYTES)
        validator = response_validator(response)
        charset = response.headers.get_content_charset() or "utf-8"
        try:
            document = document_bytes.decode(charset)
        except (LookupError, UnicodeDecodeError) as error:
            raise UpstreamError(
                f"公式リソースページをデコードできません: {charset}"
            ) from error
        final_url = response.geturl()
    link_rule = resource["archive_link"]
    if link_parser == "ax":
        # axが失敗しても別の解析器へ切り替えない。異なる解析結果が一度の
        # 更新確認へ混在し、失敗原因が隠れることを防ぐため。
        archive_urls = archive_urls_with_ax(document, link_rule, final_url, policy)
    else:
        archive_urls = archive_urls_from_html(
            document,
            link_rule["href_contains"],
            link_rule["href_suffix"],
            final_url,
            policy,
        )
    if len(archive_urls) != 1:
        raise UpstreamError(
            f"Markdown ZIPのリンクを一意に取得できません: {archive_urls!r}"
        )
    return archive_urls[0], validator


def read_source_validator(url: str, policy: SourcePolicy) -> dict[str, Any]:
    with open_source_response(url, policy, method="HEAD") as response:
        return response_validator(response)


def download_archive(
    url: str,
    destination: Path,
    policy: SourcePolicy,
) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with open_source_response(
            url,
            policy,
            require_archive=True,
            allowed_content_types=policy.archive_content_types,
        ) as response:
            validator = response_validator(response)
            declared_length = response_content_length(response)
            if declared_length is not None and declared_length > MAX_ARCHIVE_BYTES:
                raise UpstreamError(
                    "ZIPの取得サイズが上限を超えています: "
                    f"{declared_length} > {MAX_ARCHIVE_BYTES}"
                )
            with os.fdopen(descriptor, "wb") as output:
                descriptor = -1
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_ARCHIVE_BYTES:
                        raise UpstreamError(
                            f"ZIPの取得サイズが上限を超えています: {MAX_ARCHIVE_BYTES}"
                        )
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
        if not zipfile.is_zipfile(temporary_path):
            raise UpstreamError("取得したファイルは有効なZIPではありません")
        os.replace(temporary_path, destination)
        return validator
    finally:
        if descriptor != -1:
            os.close(descriptor)
        if temporary_path.exists():
            temporary_path.unlink()


def extract_archive(archive: Path, destination: Path) -> Path:
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > MAX_ARCHIVE_ENTRIES:
            raise UpstreamError(f"ZIPのエントリ数が上限を超えています: {len(members)}")

        seen_paths: set[str] = set()
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
            seen_paths.add(comparable_path)

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
    policy: SourcePolicy,
    resource_validator: dict[str, Any],
    link_parser: str,
) -> dict[str, Any]:
    validators: dict[str, Any] = {
        "link_parser": link_parser,
        "resources_page": resource_validator,
    }
    for name, source in contract["sources"].items():
        if name != "resources_page":
            validators[name] = read_source_validator(source["url"], policy)
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
        try:
            policy = source_policy(contract)
            link_parser = resolve_link_parser(getattr(arguments, "link_parser", "auto"))
            archive_url, resource_validator = find_current_archive(
                contract, policy, link_parser
            )
            validators = source_validators(
                contract, policy, resource_validator, link_parser
            )
            active_archive_url = manifest["active_snapshot"]["archive"]["url"]
            active_archive_sha256 = manifest["active_snapshot"]["archive"]["sha256"]
            result: dict[str, Any]

            with tempfile.TemporaryDirectory(prefix="dads-update-") as temporary:
                temporary_dir = Path(temporary)
                archive_file = temporary_dir / "candidate.zip"
                archive_validator = download_archive(archive_url, archive_file, policy)
                archive_url = archive_validator["url"]
                archive_sha256 = sha256_file(archive_file)
                archive_validator["sha256"] = archive_sha256
                validators["archive"] = archive_validator

                if (
                    archive_url == active_archive_url
                    and archive_sha256 == active_archive_sha256
                ):
                    result = {
                        "ok": True,
                        "result": "unchanged",
                        "link_parser": link_parser,
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
                        "link_parser": link_parser,
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
    check_parser.add_argument(
        "--link-parser",
        choices=("auto", "ax", "stdlib"),
        default="auto",
        help="HTMLリンク抽出方式。autoはaxを優先し、見つからなければ標準ライブラリを使う",
    )
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
