#!/usr/bin/env python3
"""Validate and replace this installed Skill with an approved local candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import uuid
from pathlib import Path
from typing import Any

from build_index import SnapshotError, scan_snapshot, sha256_file
from skill_lock import exclusive_file_lock
from verify_snapshot import verify_snapshot

SKILL_NAME = "apply-digital-agency-design-system"
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9-]{1,64}$")
REQUIRED_PATHS = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/source-manifest.json",
    "references/foundation-map.md",
    "references/task-index.md",
    "references/update-contract.json",
    "scripts/build_index.py",
    "scripts/manage_self.py",
    "scripts/manage_upstream.py",
    "scripts/search_guidance.py",
    "scripts/skill_lock.py",
    "scripts/upstream_fetch.py",
    "scripts/verify_snapshot.py",
)
IGNORED_DIRECTORY_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
}
IGNORED_FILE_NAMES = {".DS_Store"}
IGNORED_FILE_SUFFIXES = {".pyc", ".pyo"}
WINDOWS_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class SelfUpdateError(RuntimeError):
    """Raised when a Skill candidate cannot be safely installed."""


def load_object(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise SelfUpdateError(f"JSONオブジェクトではありません: {path}")
    return value


def validate_skill_metadata(skill_root: Path) -> None:
    skill_file = skill_root / "SKILL.md"
    text = skill_file.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---(?:\n|$)", text, re.DOTALL)
    if not match:
        raise SelfUpdateError("SKILL.mdのFront Matterを解析できません")

    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            raise SelfUpdateError(f"Front Matterを解析できません: {line}")
        fields[key.strip()] = value.strip()

    unexpected = set(fields) - {"description", "name"}
    if unexpected:
        raise SelfUpdateError(
            f"未対応のFront Matter項目です: {', '.join(sorted(unexpected))}"
        )
    if fields.get("name") != SKILL_NAME:
        raise SelfUpdateError(f"Skill名が一致しません: {fields.get('name')!r}")
    if not SKILL_NAME_PATTERN.fullmatch(fields["name"]):
        raise SelfUpdateError("Skill名がhyphen-caseではありません")
    if (
        fields["name"].startswith("-")
        or fields["name"].endswith("-")
        or "--" in fields["name"]
    ):
        raise SelfUpdateError("Skill名のハイフン位置が不正です")
    description = fields.get("description", "")
    if (
        not description
        or len(description) > 1024
        or "<" in description
        or ">" in description
    ):
        raise SelfUpdateError("Skillのdescriptionが不正です")


def validate_regular_tree(skill_root: Path) -> None:
    """Reject links and special files before reading or copying a candidate."""
    root_metadata = skill_root.lstat()
    if getattr(root_metadata, "st_file_attributes", 0) & WINDOWS_REPARSE_POINT:
        raise SelfUpdateError(f"Windowsの再解析ポイントは使えません: {skill_root}")
    for directory, directory_names, file_names in os.walk(
        skill_root, topdown=True, followlinks=False
    ):
        directory_path = Path(directory)
        for name in directory_names:
            path = directory_path / name
            metadata = path.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or getattr(metadata, "st_file_attributes", 0) & WINDOWS_REPARSE_POINT
            ):
                raise SelfUpdateError(
                    f"リンクまたは特殊ディレクトリは使えません: {path}"
                )
        for name in file_names:
            path = directory_path / name
            metadata = path.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or getattr(metadata, "st_file_attributes", 0) & WINDOWS_REPARSE_POINT
            ):
                raise SelfUpdateError(f"リンクまたは特殊ファイルは使えません: {path}")


def validate_required_paths(skill_root: Path) -> None:
    if not skill_root.is_dir() or skill_root.is_symlink():
        raise SelfUpdateError(f"通常のSkillディレクトリではありません: {skill_root}")
    validate_regular_tree(skill_root)
    missing = [path for path in REQUIRED_PATHS if not (skill_root / path).is_file()]
    if missing:
        raise SelfUpdateError(f"Skillの必須ファイルがありません: {', '.join(missing)}")
    validate_skill_metadata(skill_root)


def resolve_reference_path(references_root: Path, raw_path: object, label: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise SelfUpdateError(f"{label}が不正です")
    relative = Path(raw_path)
    if relative.is_absolute():
        raise SelfUpdateError(f"{label}に絶対パスは使えません")
    resolved_root = references_root.resolve()
    resolved = (resolved_root / relative).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise SelfUpdateError(f"{label}がreferencesの外を指しています") from error
    return resolved


def validate_snapshot(skill_root: Path) -> dict[str, Any]:
    references_root = skill_root / "references"
    manifest = load_object(references_root / "source-manifest.json")
    try:
        active = manifest["active_snapshot"]
        snapshot_dir = resolve_reference_path(
            references_root, active["path"], "active_snapshot.path"
        )
        index_file = resolve_reference_path(
            references_root, active["index_path"], "active_snapshot.index_path"
        )
        expected_index = active["index_sha256"]
        expected_tree = active["corpus"]["tree_sha256"]
        archive_sha256 = active["archive"]["sha256"]
    except (KeyError, TypeError) as error:
        raise SelfUpdateError("source-manifest.jsonの構造が不正です") from error

    if (
        snapshot_dir.parent.name != "upstream"
        or snapshot_dir.parent.parent != references_root.resolve()
    ):
        raise SelfUpdateError("有効スナップショットの配置が不正です")
    if index_file != snapshot_dir / "source-index.json":
        raise SelfUpdateError("有効スナップショットの索引配置が不正です")
    if not isinstance(expected_index, str) or not re.fullmatch(
        r"[0-9a-f]{64}", expected_index
    ):
        raise SelfUpdateError("公式Markdown索引のSHA-256記録が不正です")
    actual_index = sha256_file(index_file)
    if actual_index != expected_index:
        raise SelfUpdateError(
            f"公式Markdown索引のSHA-256が一致しません: "
            f"expected={expected_index}, actual={actual_index}"
        )
    result = verify_snapshot(snapshot_dir, index_file)
    if not result["ok"]:
        raise SelfUpdateError(
            "公式Markdownの検証に失敗しました: " + "; ".join(result["errors"])
        )
    actual_tree = scan_snapshot(snapshot_dir)["tree_sha256"]
    if actual_tree != expected_tree:
        raise SelfUpdateError(
            f"公式Markdownのツリーハッシュが一致しません: expected={expected_tree}, actual={actual_tree}"
        )
    if not isinstance(archive_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", archive_sha256
    ):
        raise SelfUpdateError("公式ZIPのSHA-256記録が不正です")
    return {
        "tree_sha256": actual_tree,
        "index_sha256": actual_index,
        "archive_sha256": archive_sha256,
    }


def normalize_skill_root(path: Path, label: str) -> Path:
    absolute = path if path.is_absolute() else Path.cwd() / path
    try:
        metadata = absolute.lstat()
    except OSError as error:
        raise SelfUpdateError(f"{label}を解決できません: {absolute}") from error
    if stat.S_ISLNK(metadata.st_mode):
        raise SelfUpdateError(f"{label}にシンボリックリンクは使えません")
    if getattr(metadata, "st_file_attributes", 0) & WINDOWS_REPARSE_POINT:
        raise SelfUpdateError(f"{label}にWindowsの再解析ポイントは使えません")
    return absolute.resolve(strict=True)


def validate_candidate(current_root: Path, candidate_root: Path) -> dict[str, Any]:
    current_root = normalize_skill_root(current_root, "現在版")
    candidate_root = normalize_skill_root(candidate_root, "更新候補")
    if current_root == candidate_root:
        raise SelfUpdateError("現在版を更新候補として指定できません")
    validate_required_paths(current_root)
    validate_required_paths(candidate_root)
    current_snapshot = validate_snapshot(current_root)
    candidate_snapshot = validate_snapshot(candidate_root)
    if candidate_snapshot != current_snapshot:
        raise SelfUpdateError(
            "Skill本体の更新候補に異なる公式資料が含まれています。公式資料更新として別に確認してください"
        )
    return {
        "ok": True,
        "result": "candidate_valid",
        "current_skill": str(current_root),
        "candidate_skill": str(candidate_root),
        "current_skill_sha256": skill_tree_sha256(current_root),
        "candidate_skill_sha256": skill_tree_sha256(candidate_root),
        "official_snapshot": current_snapshot,
    }


def should_ignore(path: Path) -> bool:
    return (
        any(part in IGNORED_DIRECTORY_NAMES for part in path.parts)
        or path.name in IGNORED_FILE_NAMES
        or path.suffix in IGNORED_FILE_SUFFIXES
    )


def skill_tree_sha256(skill_root: Path) -> str:
    """Hash every distributed file while excluding local caches."""
    validate_regular_tree(skill_root)
    digest = hashlib.sha256()
    paths = sorted(
        (
            path
            for path in skill_root.rglob("*")
            if path.is_file() and not should_ignore(path.relative_to(skill_root))
        ),
        key=lambda path: path.relative_to(skill_root).as_posix(),
    )
    for path in paths:
        relative_path = path.relative_to(skill_root).as_posix()
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def copy_skill(source: Path, destination: Path) -> None:
    def ignore(directory: str, names: list[str]) -> set[str]:
        directory_path = Path(directory)
        return {
            name
            for name in names
            if should_ignore((directory_path / name).relative_to(source))
        }

    shutil.copytree(source, destination, ignore=ignore)


def validate_expected_hash(actual: str, expected: str, label: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise SelfUpdateError(f"{label}の期待SHA-256が不正です")
    if actual != expected:
        raise SelfUpdateError(
            f"{label}が承認後に変更されました: expected={expected}, actual={actual}"
        )


def replace_skill(
    current_root: Path,
    candidate_root: Path,
    expected_current_sha256: str,
    expected_candidate_sha256: str,
) -> dict[str, Any]:
    current_root = normalize_skill_root(current_root, "現在版")
    candidate_root = normalize_skill_root(candidate_root, "更新候補")
    lock_file = current_root.parent / f".{current_root.name}.update.lock"
    with exclusive_file_lock(lock_file):
        return replace_skill_locked(
            current_root,
            candidate_root,
            expected_current_sha256,
            expected_candidate_sha256,
        )


def replace_skill_locked(
    current_root: Path,
    candidate_root: Path,
    expected_current_sha256: str,
    expected_candidate_sha256: str,
) -> dict[str, Any]:
    validation = validate_candidate(current_root, candidate_root)
    validate_expected_hash(
        validation["current_skill_sha256"],
        expected_current_sha256,
        "現在版Skill",
    )
    validate_expected_hash(
        validation["candidate_skill_sha256"],
        expected_candidate_sha256,
        "更新候補Skill",
    )
    parent = current_root.parent
    token = uuid.uuid4().hex
    staging = parent / f".{current_root.name}.staging-{token}"
    backup = parent / f".{current_root.name}.backup-{token}"

    backup_created = False
    cleanup_warning = None

    def restore_backup(failed: Path) -> None:
        nonlocal backup_created
        deferred_interrupt = None
        try:
            while backup.exists():
                try:
                    if current_root.exists():
                        os.replace(current_root, failed)
                    if not current_root.exists() and backup.exists():
                        os.replace(backup, current_root)
                except (KeyboardInterrupt, SystemExit) as interruption:
                    # Re-read filesystem state and finish restoring before the
                    # original interruption is allowed to escape.
                    deferred_interrupt = deferred_interrupt or interruption
                    continue
            backup_created = False
        except OSError as restore_error:
            raise SelfUpdateError(
                f"旧版の復元に失敗しました。"
                f"旧版は{backup}に残っています: {restore_error}"
            ) from restore_error
        finally:
            if current_root.exists() and not backup.exists() and failed.exists():
                shutil.rmtree(failed, ignore_errors=True)
        if deferred_interrupt is not None:
            # The caller already has an original exception to re-raise. This
            # exception only records an interruption encountered during repair.
            return

    try:
        copy_skill(candidate_root, staging)
        validate_required_paths(staging)
        staged_snapshot = validate_snapshot(staging)
        if staged_snapshot != validation["official_snapshot"]:
            raise SelfUpdateError("更新候補の公式資料が承認後に変更されました")
        validate_expected_hash(
            skill_tree_sha256(staging),
            expected_candidate_sha256,
            "更新候補Skill",
        )
        validate_expected_hash(
            skill_tree_sha256(current_root),
            expected_current_sha256,
            "現在版Skill",
        )
        failed = parent / f".{current_root.name}.failed-{token}"
        try:
            os.replace(current_root, backup)
            backup_created = True
            os.replace(staging, current_root)
        except BaseException:
            # A signal may arrive after rename succeeds but before the following
            # Python assignment. The filesystem is the authoritative state.
            if backup.exists():
                backup_created = True
                restore_backup(failed)
            raise
        try:
            validate_required_paths(current_root)
            validate_snapshot(current_root)
            validate_expected_hash(
                skill_tree_sha256(current_root),
                expected_candidate_sha256,
                "置換後Skill",
            )
        # Roll back on validation errors and on process-level interruptions alike.
        except BaseException:
            restore_backup(failed)
            raise
        try:
            shutil.rmtree(backup)
            backup_created = False
        except OSError as error:
            cleanup_warning = (
                f"置換は成功しましたが、バックアップを削除できません: {backup}: {error}"
            )
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    return {
        **validation,
        "result": "updated",
        "installed_skill": str(current_root),
        "backup_retained": str(backup) if backup_created else None,
        "warning": cleanup_warning,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate-candidate", "install-candidate"))
    parser.add_argument("--current-skill", type=Path, required=True)
    parser.add_argument("--candidate-skill", type=Path, required=True)
    parser.add_argument("--expected-current-sha256")
    parser.add_argument("--expected-candidate-sha256")
    parser.add_argument("--human-approved", action="store_true")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    try:
        if arguments.command == "validate-candidate":
            result = validate_candidate(
                arguments.current_skill, arguments.candidate_skill
            )
        else:
            if not arguments.human_approved:
                raise SelfUpdateError("Skill本体の置換には利用者の承認が必要です")
            if not arguments.expected_current_sha256:
                raise SelfUpdateError("現在版Skillの期待SHA-256が必要です")
            if not arguments.expected_candidate_sha256:
                raise SelfUpdateError("更新候補Skillの期待SHA-256が必要です")
            result = replace_skill(
                arguments.current_skill,
                arguments.candidate_skill,
                arguments.expected_current_sha256,
                arguments.expected_candidate_sha256,
            )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        shutil.Error,
        SnapshotError,
        SelfUpdateError,
    ) as error:
        result = {"ok": False, "error": str(error)}

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
