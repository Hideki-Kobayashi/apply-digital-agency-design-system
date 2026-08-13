#!/usr/bin/env python3
"""Search the active DADS snapshot and return ranked official documents."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

UPDATE_TERMS = {"更新", "変更", "差分", "履歴", "rev", "revision", "changelog"}


def load_object(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise TypeError(f"JSONオブジェクトではありません: {path}")
    return value


def query_terms(query: str) -> list[str]:
    terms = [term.casefold() for term in re.split(r"[\s,、/]+", query) if term]
    if not terms:
        raise ValueError("検索語が空です")
    return terms


def count_matches(text: str, terms: list[str]) -> int:
    normalized = text.casefold()
    return sum(normalized.count(term) for term in terms)


def search(
    query: str,
    manifest_file: Path,
    index_file: Path | None,
    limit: int,
) -> list[dict[str, Any]]:
    manifest = load_object(manifest_file)
    if index_file is None:
        index_file = manifest_file.parent / manifest["active_snapshot"]["index_path"]
    index = load_object(index_file)
    active_path = manifest["active_snapshot"]["path"]
    snapshot_dir = (manifest_file.parent / active_path).resolve()
    terms = query_terms(query)
    wants_history = any(term in UPDATE_TERMS for term in terms)
    results: list[dict[str, Any]] = []

    for entry in index.get("files", []):
        if not entry.get("official"):
            continue

        title = entry.get("title", "")
        slug = entry.get("slug", "")
        category = entry.get("category", "")
        document_type = entry.get("document_type", "")
        body = (snapshot_dir / entry["path"]).read_text(encoding="utf-8")

        title_matches = count_matches(title, terms)
        slug_matches = count_matches(slug, terms)
        category_matches = count_matches(category, terms)
        body_matches = count_matches(body, terms)
        searchable_text = f"{title} {slug} {category} {body}".casefold()
        matched_terms = sum(1 for term in terms if term in searchable_text)
        score = (
            matched_terms * 30
            + title_matches * 20
            + slug_matches * 12
            + category_matches * 6
            + min(body_matches, 20)
        )
        if document_type == "changelog" and not wants_history:
            score -= 12
        if score <= 0:
            continue

        results.append(
            {
                "score": score,
                "title": title,
                "document_type": document_type,
                "path": str(snapshot_dir / entry["path"]),
                "source_url": entry["source_url"],
                "matched_terms": matched_terms,
            }
        )

    results.sort(key=lambda item: (-item["score"], item["path"]))
    return results[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument("--manifest-file", type=Path, required=True)
    parser.add_argument("--index-file", type=Path)
    parser.add_argument("--limit", type=int, default=10)
    arguments = parser.parse_args()

    try:
        results = search(
            query=arguments.query,
            manifest_file=arguments.manifest_file.resolve(),
            index_file=arguments.index_file.resolve() if arguments.index_file else None,
            limit=max(1, arguments.limit),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1

    print(json.dumps({"ok": True, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
