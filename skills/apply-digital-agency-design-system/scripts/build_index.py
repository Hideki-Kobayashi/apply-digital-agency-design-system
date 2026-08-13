#!/usr/bin/env python3
"""Build a deterministic index from a DADS Markdown snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = (
    "title",
    "category",
    "slug",
    "document_type",
    "source_url",
    "language",
)
OFFICIAL_URL_PREFIX = "https://design.digital.go.jp/dads/"


class SnapshotError(ValueError):
    """Raised when the snapshot does not satisfy its input contract."""


def parse_front_matter(path: Path) -> dict[str, str] | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None

    closing = text.find("\n---\n", 4)
    if closing < 0:
        raise SnapshotError(f"Front Matterが閉じられていません: {path}")

    metadata: dict[str, str] = {}
    for line in text[4:closing].splitlines():
        if not line.strip():
            continue
        key, separator, raw_value = line.partition(":")
        if not separator:
            raise SnapshotError(f"Front Matterを解析できません: {path}: {line}")
        value = raw_value.strip()
        if value.startswith('"') and value.endswith('"'):
            value = json.loads(value)
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        metadata[key.strip()] = value
    return metadata


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_source_url(url: str) -> str:
    normalized = url.strip().split("#", 1)[0]
    if not normalized.endswith("/"):
        normalized += "/"
    return normalized


def scan_snapshot(snapshot_dir: Path) -> dict[str, Any]:
    if not snapshot_dir.is_dir():
        raise SnapshotError(f"スナップショットが見つかりません: {snapshot_dir}")

    files: list[dict[str, Any]] = []
    source_urls: dict[str, str] = {}
    official_count = 0

    for path in sorted(snapshot_dir.rglob("*.md")):
        relative_path = path.relative_to(snapshot_dir).as_posix()
        metadata = parse_front_matter(path)
        entry: dict[str, Any] = {
            "path": relative_path,
            "sha256": sha256_file(path),
            "official": metadata is not None,
        }

        if metadata is not None:
            missing = [field for field in REQUIRED_FIELDS if field not in metadata]
            if missing:
                raise SnapshotError(
                    f"必須Front Matterがありません: {relative_path}: {', '.join(missing)}"
                )
            source_url = normalize_source_url(metadata["source_url"])
            if not source_url.startswith(OFFICIAL_URL_PREFIX):
                raise SnapshotError(
                    f"公式外のsource_urlです: {relative_path}: {source_url}"
                )
            if source_url in source_urls:
                raise SnapshotError(
                    "source_urlが重複しています: "
                    f"{source_urls[source_url]} / {relative_path}: {source_url}"
                )
            source_urls[source_url] = relative_path
            official_count += 1
            entry.update(
                {
                    "document_id": source_url,
                    "title": metadata["title"],
                    "category": metadata["category"],
                    "slug": metadata["slug"],
                    "document_type": metadata["document_type"],
                    "source_url": source_url,
                    "language": metadata["language"],
                }
            )

        files.append(entry)

    tree_digest = hashlib.sha256()
    for entry in files:
        tree_digest.update(entry["path"].encode("utf-8"))
        tree_digest.update(b"\0")
        tree_digest.update(entry["sha256"].encode("ascii"))
        tree_digest.update(b"\n")

    root_index = snapshot_dir / "index.md"
    dads_version = None
    if root_index.exists():
        match = re.search(
            r"^# .*?\b(v\d+(?:\.\d+){2})\b",
            root_index.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        if match:
            dads_version = match.group(1)

    return {
        "schema_version": 1,
        "markdown_count": len(files),
        "official_document_count": official_count,
        "auxiliary_document_count": len(files) - official_count,
        "dads_version": dads_version,
        "tree_sha256": tree_digest.hexdigest(),
        "files": files,
    }


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent, text=True
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    try:
        index = scan_snapshot(arguments.snapshot_dir.resolve())
    except (OSError, SnapshotError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1

    if arguments.output:
        atomic_write_json(arguments.output.resolve(), index)
    else:
        print(json.dumps(index, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
