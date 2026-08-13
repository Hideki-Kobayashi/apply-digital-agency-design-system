from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

import manage_upstream


class StatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.contract_file = self.root / "contract.json"
        self.state_file = self.root / "state.json"
        self.contract_file.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "contract_version": 3,
                    "freshness_days": 30,
                }
            ),
            encoding="utf-8",
        )
        self.now = dt.datetime(2026, 8, 12, 6, 0, tzinfo=dt.timezone.utc)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_state(self, checked_at: dt.datetime, contract_version: int = 3) -> None:
        self.state_file.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "checked_contract_version": contract_version,
                    "last_successful_check_at": manage_upstream.format_time(checked_at),
                }
            ),
            encoding="utf-8",
        )

    def test_just_before_30_days_is_fresh(self) -> None:
        self.write_state(self.now - dt.timedelta(days=30) + dt.timedelta(seconds=1))
        result = manage_upstream.status_result(
            self.state_file, self.contract_file, self.now
        )
        self.assertEqual("fresh", result["status"])
        self.assertFalse(result["network_accessed"])

    def test_exactly_30_days_is_due(self) -> None:
        self.write_state(self.now - dt.timedelta(days=30))
        result = manage_upstream.status_result(
            self.state_file, self.contract_file, self.now
        )
        self.assertEqual("due", result["status"])

    def test_missing_state_is_never_checked(self) -> None:
        result = manage_upstream.status_result(
            self.state_file, self.contract_file, self.now
        )
        self.assertEqual("never_checked", result["status"])

    def test_contract_change_is_unknown(self) -> None:
        self.write_state(self.now, contract_version=2)
        result = manage_upstream.status_result(
            self.state_file, self.contract_file, self.now
        )
        self.assertEqual("unknown", result["status"])
        self.assertEqual("contract_version_changed", result["reason"])

    def test_future_success_is_unknown(self) -> None:
        self.write_state(self.now + dt.timedelta(seconds=1))
        result = manage_upstream.status_result(
            self.state_file, self.contract_file, self.now
        )
        self.assertEqual("unknown", result["status"])
        self.assertEqual("successful_check_is_in_future", result["reason"])

    def test_check_without_consent_never_calls_network(self) -> None:
        arguments = argparse.Namespace(network_approved=False)
        with (
            mock.patch.object(manage_upstream, "select_fetch_backend") as network,
            self.assertRaises(manage_upstream.UpstreamError),
        ):
            manage_upstream.check_upstream(arguments)
        network.assert_not_called()

    def test_fresh_check_skips_network_without_force(self) -> None:
        self.write_state(self.now)
        manifest_file = self.root / "manifest.json"
        manifest_file.write_text(
            json.dumps({"active_snapshot": {"id": "current"}}),
            encoding="utf-8",
        )
        arguments = argparse.Namespace(
            network_approved=True,
            force=False,
            state_file=self.state_file,
            contract_file=self.contract_file,
            manifest_file=manifest_file,
        )
        with (
            mock.patch.object(manage_upstream, "utc_now", return_value=self.now),
            mock.patch.object(manage_upstream, "select_fetch_backend") as network,
        ):
            result = manage_upstream.check_upstream(arguments)
        self.assertEqual("skipped_fresh", result["result"])
        network.assert_not_called()


class DefaultPathTests(unittest.TestCase):
    def test_state_directory_can_be_overridden(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.dict(
                os.environ,
                {manage_upstream.STATE_DIR_ENV: temporary},
            ),
        ):
            self.assertEqual(
                Path(temporary) / "update-status.json",
                manage_upstream.default_state_file(),
            )

    def test_cli_defaults_keep_runtime_files_outside_skill(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.dict(
                os.environ,
                {manage_upstream.STATE_DIR_ENV: temporary},
            ),
        ):
            arguments = manage_upstream.build_parser().parse_args(["status"])
        self.assertEqual(Path(temporary) / "update-status.json", arguments.state_file)
        self.assertEqual(
            manage_upstream.SKILL_ROOT / "references/update-contract.json",
            arguments.contract_file,
        )

    def test_check_uses_automatic_fetch_backend_by_default(self) -> None:
        arguments = manage_upstream.build_parser().parse_args(
            ["check", "--network-approved"]
        )
        self.assertEqual("auto", arguments.fetch_backend)


class CheckBackendFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.state_file = self.root / "state.json"
        self.contract_file = self.root / "contract.json"
        self.manifest_file = self.root / "manifest.json"
        self.candidate_root = self.root / "candidates"
        self.archive_url = (
            "https://design.digital.go.jp/dads/dads-markdown-20260805.zip"
        )
        self.payload = b"unchanged archive"
        self.contract_file.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "contract_version": 3,
                    "freshness_days": 30,
                }
            ),
            encoding="utf-8",
        )
        self.manifest_file.write_text(
            json.dumps(
                {
                    "active_snapshot": {
                        "id": "current",
                        "archive": {
                            "url": self.archive_url,
                            "sha256": hashlib.sha256(self.payload).hexdigest(),
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        self.arguments = argparse.Namespace(
            network_approved=True,
            force=False,
            fetch_backend="auto",
            state_file=self.state_file,
            contract_file=self.contract_file,
            manifest_file=self.manifest_file,
            candidate_root=self.candidate_root,
        )
        self.now = dt.datetime(2026, 8, 13, 0, 0, tzinfo=dt.timezone.utc)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_one_selected_backend_handles_discovery_and_download(self) -> None:
        calls: list[str] = []
        payload = self.payload
        archive_url = self.archive_url

        class RecordingBackend:
            name = "ax"

            def find_current_archive(self, _contract: dict) -> str:
                calls.append("find")
                return archive_url

            def download_archive(self, _url: str, destination: Path) -> dict:
                calls.append("download")
                destination.write_bytes(payload)
                return {"url": archive_url, "bytes": len(payload)}

        with (
            mock.patch.object(
                manage_upstream,
                "select_fetch_backend",
                return_value=RecordingBackend(),
            ) as select,
            mock.patch.object(
                manage_upstream,
                "utc_now",
                side_effect=(self.now, self.now + dt.timedelta(seconds=1)),
            ),
        ):
            result = manage_upstream.check_upstream(self.arguments)

        self.assertEqual(["find", "download"], calls)
        select.assert_called_once_with("auto", mock.ANY)
        self.assertEqual("unchanged", result["result"])
        self.assertEqual("ax", result["fetch_backend"])
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertEqual(
            {
                "fetch_backend": "ax",
                "archive": {
                    "url": self.archive_url,
                    "bytes": len(self.payload),
                    "sha256": hashlib.sha256(self.payload).hexdigest(),
                },
            },
            state["source_verification"],
        )
        self.assertNotIn("source_validators", state)

    def test_failed_backend_does_not_replace_the_last_success_time(self) -> None:
        last_success = self.now - dt.timedelta(days=31)
        self.state_file.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "checked_contract_version": 3,
                    "last_successful_check_at": manage_upstream.format_time(
                        last_success
                    ),
                    "active_snapshot_id": "current",
                    "pending_candidate_ids": [],
                }
            ),
            encoding="utf-8",
        )
        backend = mock.Mock(name="selected_backend")
        backend.find_current_archive.side_effect = manage_upstream.UpstreamError(
            "selected backend failed"
        )
        with (
            mock.patch.object(
                manage_upstream,
                "select_fetch_backend",
                return_value=backend,
            ) as select,
            mock.patch.object(manage_upstream, "utc_now", return_value=self.now),
            self.assertRaisesRegex(
                manage_upstream.UpstreamError, "selected backend failed"
            ),
        ):
            manage_upstream.check_upstream(self.arguments)

        select.assert_called_once()
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertEqual(
            manage_upstream.format_time(last_success),
            state["last_successful_check_at"],
        )
        self.assertEqual("failed", state["last_check_result"])


class ArchiveExtractionTests(unittest.TestCase):
    def test_valid_snapshot_extracts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "snapshot.zip"
            destination = root / "extracted"
            destination.mkdir()
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("README.md", "fixture")
                bundle.writestr("index.md", "# fixture")
            snapshot = manage_upstream.extract_archive(archive, destination)
            self.assertEqual(destination, snapshot)

    def test_backslash_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "snapshot.zip"
            destination = root / "extracted"
            destination.mkdir()
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("folder\\index.md", "fixture")
            with self.assertRaises(manage_upstream.UpstreamError):
                manage_upstream.extract_archive(archive, destination)

    def test_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "snapshot.zip"
            destination = root / "extracted"
            destination.mkdir()
            symlink = zipfile.ZipInfo("index.md")
            symlink.create_system = 3
            symlink.external_attr = 0o120777 << 16
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr(symlink, "README.md")
            with self.assertRaises(manage_upstream.UpstreamError):
                manage_upstream.extract_archive(archive, destination)

    def test_windows_unsafe_paths_are_rejected_on_every_platform(self) -> None:
        for unsafe_path in (
            "CON.md",
            "folder/NUL.txt",
            "a?.md",
            "trailing. ",
        ):
            with (
                self.subTest(path=unsafe_path),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                archive = root / "snapshot.zip"
                destination = root / "extracted"
                destination.mkdir()
                with zipfile.ZipFile(archive, "w") as bundle:
                    bundle.writestr(unsafe_path, "fixture")
                with self.assertRaises(manage_upstream.UpstreamError):
                    manage_upstream.extract_archive(archive, destination)

    def test_case_insensitive_duplicate_paths_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "snapshot.zip"
            destination = root / "extracted"
            destination.mkdir()
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("Guide.md", "first")
                bundle.writestr("guide.md", "second")
            with self.assertRaises(manage_upstream.UpstreamError):
                manage_upstream.extract_archive(archive, destination)

    def test_extracted_size_limit_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "snapshot.zip"
            destination = root / "extracted"
            destination.mkdir()
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("README.md", "fixture larger than limit")
            with (
                mock.patch.object(manage_upstream, "MAX_EXTRACTED_BYTES", 5),
                self.assertRaises(manage_upstream.UpstreamError),
            ):
                manage_upstream.extract_archive(archive, destination)


class DiffTests(unittest.TestCase):
    def test_diff_separates_added_changed_and_deleted(self) -> None:
        base = {
            "files": [
                {"path": "same.md", "sha256": "1"},
                {"path": "changed.md", "sha256": "1"},
                {"path": "deleted.md", "sha256": "1"},
            ]
        }
        candidate = {
            "files": [
                {"path": "same.md", "sha256": "1"},
                {"path": "changed.md", "sha256": "2"},
                {"path": "added.md", "sha256": "1"},
            ]
        }
        result = manage_upstream.diff_indexes(base, candidate)
        self.assertEqual(["added.md"], result["added"])
        self.assertEqual(["changed.md"], result["changed"])
        self.assertEqual(["deleted.md"], result["deleted"])


class CandidateLifecycleTests(unittest.TestCase):
    def test_candidate_creation_and_promotion_are_separate(self) -> None:
        skill_root = SCRIPTS_DIR.parent
        source_references = skill_root / "references"
        source_manifest = json.loads(
            (source_references / "source-manifest.json").read_text(encoding="utf-8")
        )
        active = source_manifest["active_snapshot"]
        source_snapshot = source_references / active["path"]
        source_index = json.loads(
            (source_references / active["index_path"]).read_text(encoding="utf-8")
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            references = root / "references"
            active_dir = references / active["path"]
            active_dir.mkdir(parents=True)
            shutil.copy2(
                source_references / active["index_path"],
                active_dir / "source-index.json",
            )
            manifest_file = references / "source-manifest.json"
            manifest_file.write_text(
                json.dumps(source_manifest),
                encoding="utf-8",
            )
            state_file = references / "update-status.json"
            original_success = "2026-08-12T00:00:00Z"
            state_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "checked_contract_version": 1,
                        "last_successful_check_at": original_success,
                        "active_snapshot_id": active["id"],
                        "pending_candidate_ids": [],
                    }
                ),
                encoding="utf-8",
            )
            archive_file = root / "candidate.zip"
            archive_file.write_bytes(b"candidate archive fixture")
            manifest_for_candidate = dict(source_manifest)
            manifest_for_candidate["_manifest_dir"] = references

            candidate_id, result, _ = manage_upstream.write_candidate(
                candidate_root=references / "candidates",
                extracted_snapshot=source_snapshot,
                archive_file=archive_file,
                archive_url="https://design.digital.go.jp/dads/dads-markdown-20260901.zip",
                base_manifest=manifest_for_candidate,
                candidate_index=source_index,
                checked_at=dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc),
            )
            self.assertEqual("candidate_created", result)
            state_before_promotion = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(active["id"], state_before_promotion["active_snapshot_id"])

            arguments = argparse.Namespace(
                human_approved=True,
                candidate_id=candidate_id,
                state_file=state_file,
                manifest_file=manifest_file,
                candidate_root=references / "candidates",
                upstream_root=references / "upstream",
            )
            promoted = manage_upstream.promote_candidate(arguments)
            self.assertEqual("promoted", promoted["result"])
            state_after_promotion = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(
                original_success, state_after_promotion["last_successful_check_at"]
            )
            self.assertNotEqual(
                active["id"], state_after_promotion["active_snapshot_id"]
            )


if __name__ == "__main__":
    unittest.main()
