from __future__ import annotations

import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
SKILL_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from build_index import scan_snapshot
from search_guidance import search
from verify_snapshot import FOUNDATION_PATHS, verify_snapshot


class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.references = SKILL_ROOT / "references"
        cls.manifest_file = cls.references / "source-manifest.json"
        cls.manifest = json.loads(cls.manifest_file.read_text(encoding="utf-8"))
        active = cls.manifest["active_snapshot"]
        cls.snapshot_dir = cls.references / active["path"]
        cls.index_file = cls.references / active["index_path"]

    def test_snapshot_contract(self) -> None:
        index = scan_snapshot(self.snapshot_dir)
        self.assertEqual(125, index["markdown_count"])
        self.assertEqual(123, index["official_document_count"])
        self.assertEqual(2, index["auxiliary_document_count"])
        self.assertEqual("v2.17.0", index["dads_version"])

    def test_source_index_order_is_platform_independent(self) -> None:
        paths = [entry["path"] for entry in scan_snapshot(self.snapshot_dir)["files"]]
        expected = sorted(paths, key=lambda path: tuple(path.split("/")))
        self.assertEqual(expected, paths)

    def test_recorded_index_matches_snapshot(self) -> None:
        result = verify_snapshot(self.snapshot_dir, self.index_file)
        self.assertTrue(result["ok"], result["errors"])

    def test_manifest_records_index_hash(self) -> None:
        digest = hashlib.sha256(self.index_file.read_bytes()).hexdigest()
        self.assertEqual(self.manifest["active_snapshot"]["index_sha256"], digest)

    def test_all_foundations_exist(self) -> None:
        actual = {
            path.relative_to(self.snapshot_dir).as_posix()
            for path in self.snapshot_dir.rglob("*.md")
        }
        self.assertEqual(set(), FOUNDATION_PATHS - actual)

    def test_task_index_routes_every_component(self) -> None:
        components = {
            path.relative_to(self.snapshot_dir).as_posix()
            for path in (self.snapshot_dir / "components").glob("*/index.md")
        }
        task_index = (self.references / "task-index.md").read_text(encoding="utf-8")
        routed = set(re.findall(r"`(components/[^`]+/index\.md)`", task_index))
        self.assertEqual(set(), components - routed)

    def test_all_routing_paths_exist(self) -> None:
        routing_text = "\n".join(
            (self.references / name).read_text(encoding="utf-8")
            for name in ("task-index.md", "foundation-map.md")
        )
        paths = set(
            re.findall(
                r"`((?:components|foundations|guidance|introduction|resources|updates|webaccessibility)/[^`]+\.md)`",
                routing_text,
            )
        )
        missing = sorted(
            path for path in paths if not (self.snapshot_dir / path).is_file()
        )
        self.assertEqual([], missing)

    def test_search_prefers_reference_document(self) -> None:
        results = search(
            "ボタン",
            self.manifest_file,
            self.index_file,
            limit=5,
        )
        self.assertEqual("ボタン", results[0]["title"])
        self.assertEqual("reference", results[0]["document_type"])


if __name__ == "__main__":
    unittest.main()
