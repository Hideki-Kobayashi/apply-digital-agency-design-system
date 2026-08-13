#!/usr/bin/env python3
"""Verify a DADS Markdown snapshot against its recorded source index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_index import SnapshotError, scan_snapshot, sha256_file

FOUNDATION_PATHS = {
    "foundations/color/index.md",
    "foundations/typography/index.md",
    "foundations/icon/index.md",
    "foundations/layout/index.md",
    "foundations/link-text/index.md",
    "foundations/spacing/index.md",
    "foundations/corner-shapes/index.md",
    "foundations/elevation/index.md",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise SnapshotError(f"JSONオブジェクトではありません: {path}")
    return value


def verify_snapshot(
    snapshot_dir: Path,
    index_file: Path | None = None,
    expected_archive_sha256: str | None = None,
    archive_file: Path | None = None,
) -> dict[str, Any]:
    actual = scan_snapshot(snapshot_dir)
    errors: list[str] = []

    actual_paths = {entry["path"] for entry in actual["files"]}
    missing_foundations = sorted(FOUNDATION_PATHS - actual_paths)
    if missing_foundations:
        errors.append(f"基本デザインが不足しています: {', '.join(missing_foundations)}")

    if index_file is not None:
        expected = load_json(index_file)
        scalar_fields = (
            "markdown_count",
            "official_document_count",
            "auxiliary_document_count",
            "dads_version",
            "tree_sha256",
        )
        for field in scalar_fields:
            if expected.get(field) != actual.get(field):
                errors.append(
                    f"{field}が一致しません: expected={expected.get(field)!r}, "
                    f"actual={actual.get(field)!r}"
                )

        expected_hashes = {
            entry["path"]: entry["sha256"] for entry in expected.get("files", [])
        }
        actual_hashes = {entry["path"]: entry["sha256"] for entry in actual["files"]}
        if expected_hashes != actual_hashes:
            added = sorted(actual_hashes.keys() - expected_hashes.keys())
            deleted = sorted(expected_hashes.keys() - actual_hashes.keys())
            changed = sorted(
                path
                for path in actual_hashes.keys() & expected_hashes.keys()
                if actual_hashes[path] != expected_hashes[path]
            )
            errors.append(
                "ファイル一覧またはハッシュが一致しません: "
                f"added={added}, changed={changed}, deleted={deleted}"
            )

    if archive_file is not None and expected_archive_sha256 is not None:
        actual_archive_sha256 = sha256_file(archive_file)
        if actual_archive_sha256 != expected_archive_sha256:
            errors.append(
                "ZIPのSHA-256が一致しません: "
                f"expected={expected_archive_sha256}, actual={actual_archive_sha256}"
            )

    return {
        "ok": not errors,
        "errors": errors,
        "summary": {
            "markdown_count": actual["markdown_count"],
            "official_document_count": actual["official_document_count"],
            "auxiliary_document_count": actual["auxiliary_document_count"],
            "dads_version": actual["dads_version"],
            "tree_sha256": actual["tree_sha256"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--index-file", type=Path)
    parser.add_argument("--archive-file", type=Path)
    parser.add_argument("--archive-sha256")
    arguments = parser.parse_args()

    try:
        result = verify_snapshot(
            snapshot_dir=arguments.snapshot_dir.resolve(),
            index_file=arguments.index_file.resolve() if arguments.index_file else None,
            expected_archive_sha256=arguments.archive_sha256,
            archive_file=arguments.archive_file.resolve()
            if arguments.archive_file
            else None,
        )
    except (OSError, json.JSONDecodeError, SnapshotError) as error:
        result = {"ok": False, "errors": [str(error)]}

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
