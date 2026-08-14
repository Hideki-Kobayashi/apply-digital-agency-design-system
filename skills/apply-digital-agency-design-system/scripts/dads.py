#!/usr/bin/env python3
"""Install and inspect the official DADS Markdown archive."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin, urlparse

SKILL_NAME = "apply-digital-agency-design-system"
RESOURCES_URL = "https://design.digital.go.jp/dads/resources/"
ARCHIVE_PATH_PATTERN = re.compile(r"^/dads/dads-markdown-([0-9]{8})\.zip$")
ARCHIVE_NAME_PATTERN = re.compile(r"^dads-markdown-([0-9]{8})\.zip$")
STATE_FILE_NAME = ".dads-state.json"
CHECK_INTERVAL = timedelta(days=30)
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_RESOURCES_PAGE_BYTES = 5 * 1024 * 1024
MAX_EXTRACTED_BYTES = 200 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 5_000
AX_TIMEOUT_SECONDS = 75
READ_CHUNK_BYTES = 1024 * 1024
WINDOWS_INVALID_CHARACTERS = frozenset('<>:"|?*')
WINDOWS_RESERVED_NAME = re.compile(
    r"^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", re.IGNORECASE
)
REQUIRED_MARKDOWN_PATHS = (
    Path("index.md"),
    Path("foundations/index.md"),
    Path("components/index.md"),
    Path("guidance/index.md"),
)


class DadsError(RuntimeError):
    """Raised when DADS data cannot be installed safely."""


def resolve_data_root(
    data_dir: Path | None = None,
    *,
    environment: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    home: Path | None = None,
) -> Path:
    """Return the configured or OS-standard data directory."""

    environment = os.environ if environment is None else environment
    platform_name = sys.platform if platform_name is None else platform_name
    home = Path.home() if home is None else home
    configured = data_dir or (
        Path(environment["DADS_SKILL_DATA_DIR"])
        if environment.get("DADS_SKILL_DATA_DIR")
        else None
    )
    if configured is not None:
        return configured.expanduser().resolve()
    if platform_name == "darwin":
        return home / "Library" / "Application Support" / SKILL_NAME
    if platform_name == "win32":
        local_app_data = environment.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else home / "AppData" / "Local"
        return base / SKILL_NAME
    xdg_data_home = environment.get("XDG_DATA_HOME")
    base = Path(xdg_data_home) if xdg_data_home else home / ".local" / "share"
    return base / SKILL_NAME


def install_data(
    data_root: Path,
    *,
    archive_url: str | None = None,
    archive_file: Path | None = None,
    network_approved: bool = False,
    replace: bool = False,
    now: datetime | None = None,
) -> dict[str, object]:
    """Install one official archive into the active data directory."""

    if (archive_url is None) == (archive_file is None):
        raise DadsError("--url または --archive-file のどちらか一方を指定してください")
    if archive_url is not None:
        archive_url = validate_archive_url(archive_url)
        if not network_approved:
            raise DadsError("URLからの取得には --network-approved が必要です")
    current_dir = data_root / "current"
    _validate_install_destination(data_root, current_dir, replace)
    data_root.mkdir(parents=True, exist_ok=True)

    # currentへの直接展開は行わない。検証失敗で利用中データが壊れるため。
    with tempfile.TemporaryDirectory(prefix=".dads-install-", dir=data_root) as temp:
        temporary_root = Path(temp)
        if archive_url is not None:
            local_archive = temporary_root / Path(urlparse(archive_url).path).name
            _download_with_ax(archive_url, local_archive)
        else:
            assert archive_file is not None
            local_archive, archive_url = _read_archive_file_source(archive_file)

        if local_archive.stat().st_size > MAX_ARCHIVE_BYTES:
            raise DadsError("ZIPのサイズが上限を超えています")
        extracted = temporary_root / "extracted"
        extracted.mkdir()
        _extract_zip(local_archive, extracted)
        content_root = _find_content_root(extracted)
        state_file = content_root / STATE_FILE_NAME
        if state_file.exists():
            raise DadsError(f"ZIP内の{STATE_FILE_NAME}と保存用ファイルが衝突します")
        checked_at = _format_timestamp(_current_time(now))
        _write_state(
            state_file,
            {
                "source_url": archive_url,
                "checked_at": checked_at,
                "latest_url": archive_url,
            },
        )
        _replace_current(content_root, current_dir)

    return {
        "installed": True,
        "current_dir": str(current_dir),
        "source_url": archive_url,
        "checked_at": checked_at,
    }


def read_status(data_root: Path, *, now: datetime | None = None) -> dict[str, object]:
    """Report the active local installation without network access."""

    current_dir = data_root / "current"
    result: dict[str, object] = {
        "installed": False,
        "data_dir": str(data_root),
        "current_dir": str(current_dir),
        "source_url": None,
        "checked_at": None,
        "latest_url": None,
        "update_available": False,
        "check_due": False,
    }
    if not current_dir.exists():
        return result
    if not current_dir.is_dir() or current_dir.is_symlink():
        raise DadsError(f"currentが通常のディレクトリではありません: {current_dir}")
    if not _has_required_structure(current_dir):
        raise DadsError(f"currentのDADS Markdown構造が不完全です: {current_dir}")
    state = _read_state(current_dir / STATE_FILE_NAME)
    source_url = state["source_url"]
    latest_url = state["latest_url"]
    checked_at = state["checked_at"]
    result.update(
        {
            "installed": True,
            "source_url": source_url,
            "checked_at": _format_timestamp(checked_at),
            "latest_url": latest_url,
            "update_available": latest_url != source_url,
            "check_due": _current_time(now) - checked_at >= CHECK_INTERVAL,
        }
    )
    return result


def check_update(
    data_root: Path,
    *,
    archive_file: Path | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Check the official resources page and record a successful result."""

    checked_time = _current_time(now)
    status = read_status(data_root, now=checked_time)
    if not status["installed"]:
        raise DadsError("DADSデータが未導入です。先にinstallを実行してください")
    if archive_file is None:
        latest_url = _find_latest_archive_with_ax()
    else:
        _, latest_url = _read_archive_file_source(archive_file)
    current_dir = data_root / "current"
    _write_state(
        current_dir / STATE_FILE_NAME,
        {
            "source_url": status["source_url"],
            "checked_at": _format_timestamp(checked_time),
            "latest_url": latest_url,
        },
    )
    result = read_status(data_root, now=checked_time)
    result["checked"] = True
    result["changed"] = result["update_available"]
    return result


def validate_archive_url(url: str) -> str:
    """Accept only the official, versioned DADS Markdown ZIP URL."""

    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError as error:
        raise DadsError(f"公式ZIP URLを解析できません: {url}") from error
    if (
        parsed.scheme != "https"
        or parsed.hostname != "design.digital.go.jp"
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or ARCHIVE_PATH_PATTERN.fullmatch(parsed.path) is None
        or parsed.query
        or parsed.fragment
    ):
        raise DadsError(f"公式DADS Markdown ZIPのURLではありません: {url}")
    return url


def _validate_install_destination(
    data_root: Path, current: Path, replace: bool
) -> None:
    if data_root.exists() and (not data_root.is_dir() or data_root.is_symlink()):
        raise DadsError(f"データ保存先が通常のディレクトリではありません: {data_root}")
    if current.exists() and (not current.is_dir() or current.is_symlink()):
        raise DadsError(f"currentが通常のディレクトリではありません: {current}")
    if current.exists() and not replace:
        raise DadsError(
            "DADSデータは導入済みです。置換する場合は --replace を指定してください"
        )
    if current.exists() and (
        not _has_required_structure(current)
        or not (current / STATE_FILE_NAME).is_file()
    ):
        raise DadsError(
            "currentはこのSkillが導入したDADSデータではないため置換できません"
        )
    if current.exists():
        _read_state(current / STATE_FILE_NAME)


def _find_latest_archive_with_ax() -> str:
    executable = shutil.which("ax")
    manual = (
        f"ブラウザで {RESOURCES_URL} を開き、Markdown ZIPをダウンロードして"
        " check --archive-file '<ZIPの絶対パス>' を実行してください"
    )
    if executable is None:
        raise DadsError(f"axが見つからず、公式の更新を確認できません。{manual}")
    try:
        completed = subprocess.run(
            [
                executable,
                RESOURCES_URL,
                'a[href*="dads-markdown-"][href$=".zip"]',
                "--row",
                "url=@href",
                "--json",
                "--all",
                "--no-cache",
                "-f",
                "--max-bytes",
                str(MAX_RESOURCES_PAGE_BYTES),
                "-m",
                "60",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=AX_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DadsError(f"axで公式の更新を確認できません: {error}。{manual}") from error
    if completed.returncode != 0:
        detail = (completed.stderr.strip() or completed.stdout.strip())[:500]
        suffix = f" ({detail})" if detail else ""
        raise DadsError(f"axで公式の更新を確認できません{suffix}。{manual}")
    try:
        rows = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise DadsError(f"axの確認結果を読み取れません。{manual}") from error
    urls: set[str] = set()
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("url"), str):
                continue
            candidate = urljoin(RESOURCES_URL, row["url"])
            try:
                urls.add(validate_archive_url(candidate))
            except DadsError:
                continue
    if not urls:
        raise DadsError(f"公式ZIPのURLを確認できません。{manual}")
    return max(urls, key=_archive_version)


def _read_archive_file_source(archive_file: Path) -> tuple[Path, str]:
    selected_archive = archive_file.expanduser()
    if selected_archive.is_symlink():
        raise DadsError(f"ZIPファイルを読み込めません: {selected_archive}")
    local_archive = selected_archive.resolve()
    if not local_archive.is_file():
        raise DadsError(f"ZIPファイルを読み込めません: {local_archive}")
    if ARCHIVE_NAME_PATTERN.fullmatch(local_archive.name) is None:
        raise DadsError(
            "手動ZIPのファイル名は dads-markdown-YYYYMMDD.zip にしてください"
        )
    source_url = validate_archive_url(
        f"https://design.digital.go.jp/dads/{local_archive.name}"
    )
    return local_archive, source_url


def _download_with_ax(url: str, destination: Path) -> None:
    executable = shutil.which("ax")
    manual = (
        f"ブラウザで {url} をダウンロードし、--archive-file に保存先を指定してください"
    )
    if executable is None:
        raise DadsError(f"axが見つかりません。{manual}")
    try:
        # シェル経由では実行しない。URLをコマンドとして解釈させないため。
        completed = subprocess.run(
            [
                executable,
                url,
                "-o",
                str(destination),
                "-f",
                "--max-bytes",
                str(MAX_ARCHIVE_BYTES),
                "-m",
                "60",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=AX_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DadsError(f"axでZIPを取得できません: {error}。{manual}") from error
    if completed.returncode != 0 or not destination.is_file():
        detail = completed.stderr.strip() or completed.stdout.strip()
        suffix = f" ({detail})" if detail else ""
        raise DadsError(f"axでZIPを取得できません{suffix}。{manual}")


def _extract_zip(archive_file: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(archive_file) as archive:
            members = archive.infolist()
            if len(members) > MAX_ARCHIVE_ENTRIES:
                raise DadsError("ZIPのファイル数が上限を超えています")
            _validate_zip_members(members)
            extracted_bytes = 0
            # extractallは使わない。検証済みパスだけを書き出すため。
            for member in members:
                relative = PurePosixPath(member.filename)
                target = destination.joinpath(*relative.parts)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("xb") as output:
                    while chunk := source.read(READ_CHUNK_BYTES):
                        extracted_bytes += len(chunk)
                        if extracted_bytes > MAX_EXTRACTED_BYTES:
                            raise DadsError("ZIP展開サイズが上限を超えました")
                        output.write(chunk)
    except DadsError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
        raise DadsError(f"ZIPを展開できません: {error}") from error


def _validate_zip_members(members: Sequence[zipfile.ZipInfo]) -> None:
    declared_bytes = 0
    for member in members:
        name = member.filename
        canonical = name.rstrip("/")
        segments = canonical.split("/")
        if (
            not canonical
            or PurePosixPath(name).is_absolute()
            or "\\" in name
            or any(
                not segment
                or segment in {".", ".."}
                or segment.endswith((" ", "."))
                or WINDOWS_RESERVED_NAME.match(segment) is not None
                or any(
                    ord(character) < 32
                    or ord(character) == 127
                    or character in WINDOWS_INVALID_CHARACTERS
                    for character in segment
                )
                for segment in segments
            )
        ):
            raise DadsError(f"ZIPに不正なパスがあります: {name}")
        file_type = (member.external_attr >> 16) & 0o170000
        if member.flag_bits & 0x1 or file_type not in (0, stat.S_IFDIR, stat.S_IFREG):
            raise DadsError(f"ZIPに展開できない項目があります: {name}")
        declared_bytes += member.file_size
        if declared_bytes > MAX_EXTRACTED_BYTES:
            raise DadsError("ZIP展開サイズが上限を超えています")


def _find_content_root(extracted: Path) -> Path:
    if _has_required_structure(extracted):
        return extracted
    entries = list(extracted.iterdir())
    matching_roots = [
        path
        for path in entries
        if path.is_dir() and not path.is_symlink() and _has_required_structure(path)
    ]
    if len(matching_roots) != 1 or entries != matching_roots:
        raise DadsError("ZIP内のDADS Markdownルートを特定できません")
    return matching_roots[0]


def _has_required_structure(directory: Path) -> bool:
    return all((directory / relative).is_file() for relative in REQUIRED_MARKDOWN_PATHS)


def _replace_current(source: Path, current: Path) -> None:
    backup: Path | None = None
    if current.exists():
        backup = Path(tempfile.mkdtemp(prefix=".current-backup-", dir=current.parent))
        backup.rmdir()
        os.replace(current, backup)
    try:
        os.replace(source, current)
    except OSError:
        if backup is not None and not current.exists():
            os.replace(backup, current)
        raise
    if backup is not None:
        shutil.rmtree(backup)


def _read_state(path: Path) -> dict[str, str | datetime]:
    if path.is_symlink():
        raise DadsError(f"{STATE_FILE_NAME}を読めません: シンボリックリンクです")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DadsError(f"{STATE_FILE_NAME}を読めません: {error}") from error
    if not isinstance(state, dict):
        raise DadsError(f"{STATE_FILE_NAME}の形式が不正です")
    source_url = state.get("source_url")
    latest_url = state.get("latest_url")
    checked_at = state.get("checked_at")
    if not all(
        isinstance(value, str) for value in (source_url, latest_url, checked_at)
    ):
        raise DadsError(f"{STATE_FILE_NAME}の形式が不正です")
    assert isinstance(source_url, str)
    assert isinstance(latest_url, str)
    assert isinstance(checked_at, str)
    return {
        "source_url": validate_archive_url(source_url),
        "latest_url": validate_archive_url(latest_url),
        "checked_at": _parse_timestamp(checked_at),
    }


def _write_state(path: Path, state: Mapping[str, object]) -> None:
    content = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        # 既存stateへの直接書き込みは行わない。中断時の破損を防ぐため。
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary_path = Path(output.name)
            output.write(content)
        os.replace(temporary_path, path)
    except OSError as error:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                # 一時ファイル削除の失敗で、元の保存エラーは置き換えない。
                pass
        raise DadsError(f"{STATE_FILE_NAME}を保存できません: {error}") from error


def _current_time(now: datetime | None) -> datetime:
    value = datetime.now(timezone.utc) if now is None else now
    if value.tzinfo is None:
        raise DadsError("時刻にタイムゾーンが必要です")
    return value.astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DadsError(f"{STATE_FILE_NAME}のchecked_atが不正です") from error
    if parsed.tzinfo is None:
        raise DadsError(f"{STATE_FILE_NAME}のchecked_atにタイムゾーンがありません")
    return parsed.astimezone(timezone.utc)


def _archive_version(url: str) -> str:
    matched = ARCHIVE_PATH_PATTERN.fullmatch(urlparse(url).path)
    assert matched is not None
    return matched.group(1)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="ローカルデータの状態を表示する")
    check = commands.add_parser("check", help="公式ページの最新ZIPを確認する")
    check.add_argument("--archive-file", type=Path)
    install = commands.add_parser("install", help="公式Markdown ZIPを導入する")
    source = install.add_mutually_exclusive_group(required=True)
    source.add_argument("--url")
    source.add_argument("--archive-file", type=Path)
    install.add_argument("--network-approved", action="store_true")
    install.add_argument("--replace", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _build_parser().parse_args(argv)
    data_root = resolve_data_root(arguments.data_dir)
    try:
        if arguments.command == "status":
            result = read_status(data_root)
        elif arguments.command == "check":
            result = check_update(data_root, archive_file=arguments.archive_file)
        else:
            result = install_data(
                data_root,
                archive_url=arguments.url,
                archive_file=arguments.archive_file,
                network_approved=arguments.network_approved,
                replace=arguments.replace,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except DadsError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
