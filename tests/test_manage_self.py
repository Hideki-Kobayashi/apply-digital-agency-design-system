from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SKILL = REPOSITORY_ROOT / "skills/apply-digital-agency-design-system"
SCRIPTS_DIR = SOURCE_SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import manage_self


class SelfUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.current = self.root / "apply-digital-agency-design-system"
        self.candidate = self.root / "candidate"
        shutil.copytree(SOURCE_SKILL, self.current)
        shutil.copytree(SOURCE_SKILL, self.candidate)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def approved_hashes(self) -> tuple[str, str]:
        result = manage_self.validate_candidate(self.current, self.candidate)
        return result["current_skill_sha256"], result["candidate_skill_sha256"]

    def replace_approved_candidate(self) -> dict:
        current_sha256, candidate_sha256 = self.approved_hashes()
        return manage_self.replace_skill(
            self.current,
            self.candidate,
            current_sha256,
            candidate_sha256,
        )

    def test_candidate_validation_is_self_contained(self) -> None:
        result = manage_self.validate_candidate(self.current, self.candidate)
        self.assertEqual("candidate_valid", result["result"])

    def test_candidate_with_different_official_snapshot_is_rejected(self) -> None:
        manifest_file = self.candidate / "references/source-manifest.json"
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest["active_snapshot"]["archive"]["sha256"] = "0" * 64
        manifest_file.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(manage_self.SelfUpdateError, "異なる公式資料"):
            manage_self.validate_candidate(self.current, self.candidate)

    def test_candidate_manifest_cannot_escape_references(self) -> None:
        manifest_file = self.candidate / "references/source-manifest.json"
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest["active_snapshot"]["path"] = "../../outside"
        manifest_file.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(manage_self.SelfUpdateError, "referencesの外"):
            manage_self.validate_candidate(self.current, self.candidate)

    def test_update_replaces_the_skill_after_validation(self) -> None:
        marker = self.candidate / "candidate-marker.txt"
        marker.write_text("new", encoding="utf-8")
        (self.current / "old-marker.txt").write_text("old", encoding="utf-8")

        result = self.replace_approved_candidate()

        self.assertEqual("updated", result["result"])
        self.assertEqual("new", (self.current / "candidate-marker.txt").read_text())
        self.assertFalse((self.current / "old-marker.txt").exists())
        self.assertEqual([], list(self.root.glob(".*.backup-*")))

    def test_failed_staging_install_restores_the_current_skill(self) -> None:
        current_sha256, candidate_sha256 = self.approved_hashes()
        original_replace = manage_self.os.replace

        def fail_candidate_install(source: Path, destination: Path) -> None:
            if ".staging-" in Path(source).name:
                raise OSError("install stopped")
            original_replace(source, destination)

        with (
            mock.patch.object(
                manage_self.os, "replace", side_effect=fail_candidate_install
            ),
            self.assertRaisesRegex(OSError, "install stopped"),
        ):
            manage_self.replace_skill(
                self.current,
                self.candidate,
                current_sha256,
                candidate_sha256,
            )

        self.assertTrue((self.current / "SKILL.md").is_file())
        self.assertEqual([], list(self.root.glob(".*.backup-*")))

    def test_interruption_after_current_move_restores_the_current_skill(self) -> None:
        current_sha256, candidate_sha256 = self.approved_hashes()
        original_replace = manage_self.os.replace
        calls = 0

        def interrupt_after_current_move(source: Path, destination: Path) -> None:
            nonlocal calls
            calls += 1
            original_replace(source, destination)
            if calls == 1:
                raise KeyboardInterrupt

        with (
            mock.patch.object(
                manage_self.os,
                "replace",
                side_effect=interrupt_after_current_move,
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            manage_self.replace_skill(
                self.current,
                self.candidate,
                current_sha256,
                candidate_sha256,
            )

        self.assertTrue((self.current / "SKILL.md").is_file())
        self.assertEqual([], list(self.root.glob(".*.backup-*")))

    def test_interruption_after_candidate_move_restores_the_current_skill(self) -> None:
        current_sha256, candidate_sha256 = self.approved_hashes()
        original_replace = manage_self.os.replace
        calls = 0

        def interrupt_after_candidate_move(source: Path, destination: Path) -> None:
            nonlocal calls
            calls += 1
            original_replace(source, destination)
            if calls == 2:
                raise KeyboardInterrupt

        with (
            mock.patch.object(
                manage_self.os,
                "replace",
                side_effect=interrupt_after_candidate_move,
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            manage_self.replace_skill(
                self.current,
                self.candidate,
                current_sha256,
                candidate_sha256,
            )

        self.assertTrue((self.current / "SKILL.md").is_file())
        self.assertEqual([], list(self.root.glob(".*.backup-*")))

    def test_interruption_while_moving_failed_candidate_still_restores(self) -> None:
        self.assert_rollback_survives_interruptions({2, 3})

    def test_interruption_while_restoring_backup_still_restores(self) -> None:
        self.assert_rollback_survives_interruptions({2, 4})

    def assert_rollback_survives_interruptions(
        self, interrupt_after_calls: set[int]
    ) -> None:
        current_sha256, candidate_sha256 = self.approved_hashes()
        original_replace = manage_self.os.replace
        calls = 0

        def interrupt_selected_moves(source: Path, destination: Path) -> None:
            nonlocal calls
            calls += 1
            original_replace(source, destination)
            if calls in interrupt_after_calls:
                raise KeyboardInterrupt

        with (
            mock.patch.object(
                manage_self.os,
                "replace",
                side_effect=interrupt_selected_moves,
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            manage_self.replace_skill(
                self.current,
                self.candidate,
                current_sha256,
                candidate_sha256,
            )

        self.assertTrue((self.current / "SKILL.md").is_file())
        self.assertEqual([], list(self.root.glob(".*.backup-*")))
        self.assertEqual([], list(self.root.glob(".*.failed-*")))

    def test_copy_failure_removes_partial_staging_directory(self) -> None:
        current_sha256, candidate_sha256 = self.approved_hashes()

        def fail_copy(source: Path, destination: Path) -> None:
            destination.mkdir()
            raise OSError("copy stopped")

        with (
            mock.patch.object(manage_self, "copy_skill", side_effect=fail_copy),
            self.assertRaisesRegex(OSError, "copy stopped"),
        ):
            manage_self.replace_skill(
                self.current,
                self.candidate,
                current_sha256,
                candidate_sha256,
            )

        self.assertTrue((self.current / "SKILL.md").is_file())
        self.assertEqual([], list(self.root.glob(".*.staging-*")))

    def test_failed_post_install_validation_restores_the_current_skill(self) -> None:
        current_sha256, candidate_sha256 = self.approved_hashes()
        original_validate_snapshot = manage_self.validate_snapshot
        calls = 0

        def fail_after_install(skill_root: Path) -> dict:
            nonlocal calls
            calls += 1
            if skill_root.resolve() == self.current.resolve() and calls > 2:
                raise manage_self.SelfUpdateError("post-install validation stopped")
            return original_validate_snapshot(skill_root)

        with (
            mock.patch.object(
                manage_self, "validate_snapshot", side_effect=fail_after_install
            ),
            self.assertRaisesRegex(
                manage_self.SelfUpdateError, "post-install validation stopped"
            ),
        ):
            manage_self.replace_skill(
                self.current,
                self.candidate,
                current_sha256,
                candidate_sha256,
            )

        self.assertTrue((self.current / "SKILL.md").is_file())
        self.assertEqual([], list(self.root.glob(".*.backup-*")))

    def test_candidate_change_after_approval_is_rejected(self) -> None:
        current_sha256, candidate_sha256 = self.approved_hashes()
        original_copy = manage_self.copy_skill

        def mutate_then_copy(source: Path, destination: Path) -> None:
            (source / "changed-after-approval.txt").write_text(
                "changed", encoding="utf-8"
            )
            original_copy(source, destination)

        with (
            mock.patch.object(manage_self, "copy_skill", side_effect=mutate_then_copy),
            self.assertRaisesRegex(manage_self.SelfUpdateError, "承認後に変更"),
        ):
            manage_self.replace_skill(
                self.current,
                self.candidate,
                current_sha256,
                candidate_sha256,
            )

        self.assertTrue((self.current / "SKILL.md").is_file())
        self.assertFalse((self.current / "changed-after-approval.txt").exists())
        self.assertEqual([], list(self.root.glob(".*.staging-*")))


if __name__ == "__main__":
    unittest.main()
