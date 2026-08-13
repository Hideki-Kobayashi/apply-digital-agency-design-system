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

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPOSITORY_ROOT / "skills/apply-digital-agency-design-system"
SCRIPTS_DIR = SKILL_ROOT / "scripts"
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
                    "allowed_hosts": ["design.digital.go.jp"],
                    "allowed_path_prefixes": ["/dads/"],
                    "archive_path_pattern": (r"^/dads/dads-markdown-[0-9]{8}\.zip$"),
                    "sources": {
                        "resources_page": {
                            "url": "https://design.digital.go.jp/dads/resources/"
                        }
                    },
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
                return_value=self.now,
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
                "acquisition_method": "automatic",
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

    def test_download_failure_offers_the_discovered_official_url(self) -> None:
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
        backend.name = "ax"
        backend.find_current_archive.return_value = self.archive_url
        backend.download_archive.side_effect = manage_upstream.UpstreamError(
            "automatic download failed"
        )

        with (
            mock.patch.object(
                manage_upstream,
                "select_fetch_backend",
                return_value=backend,
            ),
            mock.patch.object(manage_upstream, "utc_now", return_value=self.now),
            self.assertRaises(manage_upstream.ManualDownloadRequired) as raised,
        ):
            manage_upstream.check_upstream(self.arguments)

        result = raised.exception.result
        self.assertFalse(result["ok"])
        self.assertEqual("manual_download_available", result["result"])
        self.assertEqual(
            self.archive_url,
            result["manual_download"]["archive_url"],
        )
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        pending = state["pending_manual_download"]
        self.assertEqual(self.archive_url, pending["archive_url"])
        self.assertEqual(
            manage_upstream.format_time(self.now), pending["discovered_at"]
        )
        self.assertEqual(3, pending["contract_version"])
        self.assertEqual("ax", pending["fetch_backend"])
        self.assertEqual(
            manage_upstream.format_time(last_success),
            state["last_successful_check_at"],
        )
        self.assertEqual("manual_download_pending", state["last_check_result"])


class ManualImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.references = self.root / "references"
        self.references.mkdir()
        self.state_file = self.root / "state.json"
        self.contract_file = self.root / "contract.json"
        self.manifest_file = self.references / "source-manifest.json"
        self.candidate_root = self.root / "candidates"
        self.active_url = "https://design.digital.go.jp/dads/dads-markdown-20260805.zip"
        self.candidate_url = (
            "https://design.digital.go.jp/dads/dads-markdown-20260813.zip"
        )
        self.now = dt.datetime(2026, 8, 13, 0, 0, tzinfo=dt.timezone.utc)
        self.discovered_at = self.now - dt.timedelta(days=1)

        self.contract_file.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "contract_version": 3,
                    "freshness_days": 30,
                    "allowed_hosts": ["design.digital.go.jp"],
                    "allowed_path_prefixes": ["/dads/"],
                    "archive_path_pattern": (r"^/dads/dads-markdown-[0-9]{8}\.zip$"),
                    "sources": {
                        "resources_page": {
                            "url": "https://design.digital.go.jp/dads/resources/",
                            "archive_link": {
                                "href_contains": "dads-markdown-",
                                "href_suffix": ".zip",
                            },
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        active_snapshot = self.references / "upstream/current"
        active_snapshot.mkdir(parents=True)
        # Keep fixture bytes identical to ZipFile.writestr on every OS.
        # Text-mode writes would turn LF into CRLF on Windows and change the
        # content hash even though the Markdown text is otherwise identical.
        (active_snapshot / "README.md").write_bytes(b"active fixture\n")
        (active_snapshot / "index.md").write_bytes(b"# DADS Markdown v2.7.0\nactive\n")
        official_file = active_snapshot / "components/example/index.md"
        official_file.parent.mkdir(parents=True)
        official_file.write_bytes(self.official_document().encode("utf-8"))
        active_index = manage_upstream.scan_snapshot(active_snapshot)
        (active_snapshot / "source-index.json").write_text(
            json.dumps(active_index),
            encoding="utf-8",
        )

        self.active_archive = self.root / "active.zip"
        self.write_archive(self.active_archive, "active")
        self.manifest_file.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "active_snapshot": {
                        "id": "current",
                        "path": "upstream/current",
                        "index_path": "upstream/current/source-index.json",
                        "archive": {
                            "url": self.active_url,
                            "sha256": manage_upstream.sha256_file(self.active_archive),
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def official_document() -> str:
        return """---
title: Example
category: Components
slug: example
document_type: reference
source_url: https://design.digital.go.jp/dads/components/example/
language: ja
---
# Example
"""

    @classmethod
    def write_archive(cls, path: Path, body: str) -> None:
        with zipfile.ZipFile(path, "w") as bundle:
            bundle.writestr("snapshot/README.md", f"{body} fixture\n")
            bundle.writestr(
                "snapshot/index.md",
                f"# DADS Markdown v2.7.0\n{body}\n",
            )
            bundle.writestr(
                "snapshot/components/example/index.md",
                cls.official_document(),
            )

    def write_state(
        self,
        archive_url: str | None = None,
        *,
        discovered_at: dt.datetime | None = None,
        contract_version: int = 3,
        last_successful_check_at: str = "2026-07-01T00:00:00Z",
    ) -> dict[str, object]:
        state: dict[str, object] = {
            "schema_version": 1,
            "checked_contract_version": 3,
            "last_successful_check_at": last_successful_check_at,
            "active_snapshot_id": "current",
            "pending_candidate_ids": [],
        }
        if archive_url is not None:
            state["pending_manual_download"] = {
                "archive_url": archive_url,
                "discovered_at": manage_upstream.format_time(
                    discovered_at or self.discovered_at
                ),
                "contract_version": contract_version,
                "fetch_backend": "ax",
            }
        self.state_file.write_text(json.dumps(state), encoding="utf-8")
        return state

    def arguments(self, archive_file: Path) -> argparse.Namespace:
        return argparse.Namespace(
            archive_file=archive_file,
            state_file=self.state_file,
            contract_file=self.contract_file,
            manifest_file=self.manifest_file,
            candidate_root=self.candidate_root,
        )

    def test_cli_exposes_manual_archive_import(self) -> None:
        arguments = manage_upstream.build_parser().parse_args(
            ["import-archive", "--archive-file", str(self.active_archive)]
        )
        self.assertEqual("import-archive", arguments.command)
        self.assertEqual(self.active_archive, arguments.archive_file)

    def test_import_requires_an_absolute_archive_path(self) -> None:
        self.write_state(self.active_url)
        with self.assertRaises(manage_upstream.UpstreamError):
            manage_upstream.import_archive(self.arguments(Path("active.zip")))

    def test_import_requires_a_pending_manual_download(self) -> None:
        self.write_state()
        with self.assertRaises(manage_upstream.UpstreamError):
            manage_upstream.import_archive(self.arguments(self.active_archive))

    def test_import_rejects_a_pending_download_from_an_old_contract(self) -> None:
        self.write_state(self.active_url, contract_version=2)
        with self.assertRaises(manage_upstream.UpstreamError):
            manage_upstream.import_archive(self.arguments(self.active_archive))

        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertIsNotNone(state["pending_manual_download"])

    def test_import_rejects_a_pending_download_outside_official_policy(
        self,
    ) -> None:
        untrusted_url = "https://example.com/dads-markdown-20260805.zip"
        previous_state = self.write_state(untrusted_url)

        with self.assertRaises(manage_upstream.UpstreamError):
            manage_upstream.import_archive(self.arguments(self.active_archive))

        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertEqual(
            previous_state["pending_manual_download"],
            state["pending_manual_download"],
        )

    def test_import_rejects_a_pending_download_older_than_freshness_window(
        self,
    ) -> None:
        stale_discovery = self.now - dt.timedelta(days=30)
        self.write_state(self.active_url, discovered_at=stale_discovery)

        with (
            mock.patch.object(manage_upstream, "utc_now", return_value=self.now),
            self.assertRaises(manage_upstream.UpstreamError),
        ):
            manage_upstream.import_archive(self.arguments(self.active_archive))

        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertIsNotNone(state["pending_manual_download"])

    def test_unchanged_import_is_offline_and_preserves_the_source_zip(self) -> None:
        self.write_state(self.active_url)
        original_bytes = self.active_archive.read_bytes()

        with (
            mock.patch.object(manage_upstream, "utc_now", return_value=self.now),
            mock.patch.object(manage_upstream, "select_fetch_backend") as network,
        ):
            result = manage_upstream.import_archive(self.arguments(self.active_archive))

        network.assert_not_called()
        self.assertEqual("unchanged", result["result"])
        self.assertEqual(original_bytes, self.active_archive.read_bytes())
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertIsNone(state["pending_manual_download"])
        self.assertEqual(
            "2026-07-01T00:00:00Z",
            state["last_successful_check_at"],
        )

    def test_changed_import_creates_a_candidate_without_promoting_it(self) -> None:
        candidate_archive = self.root / "candidate.zip"
        self.write_archive(candidate_archive, "candidate")
        original_bytes = candidate_archive.read_bytes()
        self.write_state(self.candidate_url)

        with mock.patch.object(manage_upstream, "utc_now", return_value=self.now):
            result = manage_upstream.import_archive(self.arguments(candidate_archive))

        self.assertEqual("candidate_created", result["result"])
        self.assertEqual(self.candidate_url, result["archive_url"])
        self.assertEqual(original_bytes, candidate_archive.read_bytes())
        candidate_id = result["candidate_id"]
        self.assertTrue((self.candidate_root / candidate_id).is_dir())
        candidate_manifest = json.loads(
            (self.candidate_root / candidate_id / "candidate-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            "manual_download",
            candidate_manifest["candidate_snapshot"]["archive"]["acquisition_method"],
        )
        manifest = json.loads(self.manifest_file.read_text(encoding="utf-8"))
        self.assertEqual("current", manifest["active_snapshot"]["id"])
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertIsNone(state["pending_manual_download"])
        self.assertIn(candidate_id, state["pending_candidate_ids"])
        self.assertEqual(
            "2026-07-01T00:00:00Z",
            state["last_successful_check_at"],
        )

    def test_import_rejects_untracked_files_in_the_archive(self) -> None:
        archive_file = self.root / "untracked.zip"
        with zipfile.ZipFile(archive_file, "w") as bundle:
            bundle.writestr("snapshot/README.md", "fixture\n")
            bundle.writestr("snapshot/index.md", "# DADS Markdown v2.7.0\n")
            bundle.writestr("snapshot/payload.bin", b"untracked")
        previous_state = self.write_state(self.candidate_url)

        with (
            mock.patch.object(manage_upstream, "utc_now", return_value=self.now),
            self.assertRaises(manage_upstream.UpstreamError),
        ):
            manage_upstream.import_archive(self.arguments(archive_file))

        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertEqual(
            previous_state["pending_manual_download"],
            state["pending_manual_download"],
        )

    def test_import_rejects_a_symbolic_link_source(self) -> None:
        link = self.root / "linked.zip"
        try:
            link.symlink_to(self.active_archive)
        except OSError:
            self.skipTest("symbolic links are unavailable")
        self.write_state(self.active_url)

        with self.assertRaises(manage_upstream.UpstreamError):
            manage_upstream.import_archive(self.arguments(link))

    def test_invalid_zip_keeps_pending_state_and_last_success(self) -> None:
        invalid_archive = self.root / "invalid.zip"
        invalid_archive.write_bytes(b"not a zip")
        original_bytes = invalid_archive.read_bytes()
        previous_success = "2026-07-01T00:00:00Z"
        previous_state = self.write_state(
            self.candidate_url,
            last_successful_check_at=previous_success,
        )

        with (
            mock.patch.object(manage_upstream, "utc_now", return_value=self.now),
            self.assertRaises((manage_upstream.UpstreamError, zipfile.BadZipFile)),
        ):
            manage_upstream.import_archive(self.arguments(invalid_archive))

        self.assertEqual(original_bytes, invalid_archive.read_bytes())
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertEqual(
            previous_state["pending_manual_download"],
            state["pending_manual_download"],
        )
        self.assertEqual(previous_success, state["last_successful_check_at"])

    def test_oversized_zip_keeps_pending_state_and_source_file(self) -> None:
        oversized_archive = self.root / "oversized.zip"
        oversized_archive.write_bytes(b"larger than fixture limit")
        original_bytes = oversized_archive.read_bytes()
        previous_state = self.write_state(self.candidate_url)

        with (
            mock.patch.object(manage_upstream, "utc_now", return_value=self.now),
            mock.patch.object(manage_upstream, "MAX_ARCHIVE_BYTES", 5),
            self.assertRaises(manage_upstream.UpstreamError),
        ):
            manage_upstream.import_archive(self.arguments(oversized_archive))

        self.assertEqual(original_bytes, oversized_archive.read_bytes())
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertEqual(
            previous_state["pending_manual_download"],
            state["pending_manual_download"],
        )
        self.assertEqual("manual_import_failed", state["last_check_result"])


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

    def test_file_and_directory_path_collision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "snapshot.zip"
            destination = root / "extracted"
            destination.mkdir()
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("folder", "file")
                bundle.writestr("folder/index.md", "nested")
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
            contract_file = references / "update-contract.json"
            shutil.copy2(
                source_references / "update-contract.json",
                contract_file,
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
            with zipfile.ZipFile(archive_file, "w") as archive:
                for source_file in sorted(source_snapshot.rglob("*")):
                    if source_file.is_file() and source_file.suffix == ".md":
                        relative_path = source_file.relative_to(source_snapshot)
                        archive.write(
                            source_file,
                            (Path("snapshot") / relative_path).as_posix(),
                        )
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
                contract_file=contract_file,
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

    def test_existing_candidate_is_revalidated_before_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = root / "snapshot"
            snapshot.mkdir()
            (snapshot / "README.md").write_text("fixture\n", encoding="utf-8")
            (snapshot / "index.md").write_text(
                "# DADS Markdown v2.7.0\n",
                encoding="utf-8",
            )
            for foundation in manage_upstream.verify_snapshot.__globals__[
                "FOUNDATION_PATHS"
            ]:
                path = snapshot / foundation
                path.parent.mkdir(parents=True, exist_ok=True)
                slug = path.parent.name
                path.write_text(
                    f"""---
title: {slug}
category: Foundations
slug: {slug}
document_type: reference
source_url: https://design.digital.go.jp/dads/foundations/{slug}/
language: ja
---
# {slug}
""",
                    encoding="utf-8",
                )
            candidate_index = manage_upstream.scan_snapshot(snapshot)
            references = root / "references"
            active_dir = references / "upstream/current"
            active_dir.mkdir(parents=True)
            (active_dir / "source-index.json").write_text(
                json.dumps(candidate_index),
                encoding="utf-8",
            )
            manifest = {
                "active_snapshot": {
                    "id": "current",
                    "index_path": "upstream/current/source-index.json",
                },
                "_manifest_dir": references,
            }
            archive_file = root / "candidate.zip"
            with zipfile.ZipFile(archive_file, "w") as archive:
                for source_file in sorted(snapshot.rglob("*.md")):
                    archive.write(
                        source_file,
                        (
                            Path("snapshot") / source_file.relative_to(snapshot)
                        ).as_posix(),
                    )
            candidate_root = root / "candidates"
            candidate_id, _, _ = manage_upstream.write_candidate(
                candidate_root=candidate_root,
                extracted_snapshot=snapshot,
                archive_file=archive_file,
                archive_url=(
                    "https://design.digital.go.jp/dads/dads-markdown-20260901.zip"
                ),
                base_manifest=manifest,
                candidate_index=candidate_index,
                checked_at=dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc),
            )
            (candidate_root / candidate_id / "archive.zip").write_bytes(b"tampered")

            with self.assertRaises(manage_upstream.UpstreamError):
                manage_upstream.write_candidate(
                    candidate_root=candidate_root,
                    extracted_snapshot=snapshot,
                    archive_file=archive_file,
                    archive_url=(
                        "https://design.digital.go.jp/dads/dads-markdown-20260901.zip"
                    ),
                    base_manifest=manifest,
                    candidate_index=candidate_index,
                    checked_at=dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc),
                )

    def test_legacy_candidate_manifest_is_migrated_after_full_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = root / "snapshot"
            snapshot.mkdir()
            (snapshot / "README.md").write_text("fixture\n", encoding="utf-8")
            (snapshot / "index.md").write_text(
                "# DADS Markdown v2.7.0\n",
                encoding="utf-8",
            )
            official_file = snapshot / "components/example/index.md"
            official_file.parent.mkdir(parents=True)
            official_file.write_text(
                """---
title: Example
category: Components
slug: example
document_type: reference
source_url: https://design.digital.go.jp/dads/components/example/
language: ja
---
# Example
""",
                encoding="utf-8",
            )
            candidate_index = manage_upstream.scan_snapshot(snapshot)
            references = root / "references"
            active_dir = references / "upstream/current"
            active_dir.mkdir(parents=True)
            (active_dir / "source-index.json").write_text(
                json.dumps(candidate_index),
                encoding="utf-8",
            )
            manifest = {
                "active_snapshot": {
                    "id": "current",
                    "index_path": "upstream/current/source-index.json",
                },
                "_manifest_dir": references,
            }
            archive_file = root / "candidate.zip"
            with zipfile.ZipFile(archive_file, "w") as archive:
                archive.write(snapshot / "README.md", "snapshot/README.md")
                archive.write(snapshot / "index.md", "snapshot/index.md")
                archive.write(
                    official_file,
                    "snapshot/components/example/index.md",
                )
            candidate_root = root / "candidates"
            archive_url = "https://design.digital.go.jp/dads/dads-markdown-20260901.zip"
            extracted_dir = root / "extracted"
            extracted_dir.mkdir()
            archive_snapshot = manage_upstream.extract_archive(
                archive_file,
                extracted_dir,
            )
            candidate_index = manage_upstream.scan_snapshot(archive_snapshot)
            (active_dir / "source-index.json").write_text(
                json.dumps(candidate_index),
                encoding="utf-8",
            )
            candidate_id, _, _ = manage_upstream.write_candidate(
                candidate_root=candidate_root,
                extracted_snapshot=archive_snapshot,
                archive_file=archive_file,
                archive_url=archive_url,
                base_manifest=manifest,
                candidate_index=candidate_index,
                checked_at=dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc),
            )
            manifest_file = candidate_root / candidate_id / "candidate-manifest.json"
            legacy_manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            legacy_archive = legacy_manifest["candidate_snapshot"]["archive"]
            legacy_archive["downloaded_at"] = legacy_archive.pop("acquired_at")
            legacy_archive.pop("acquisition_method")
            legacy_archive.pop("source_url")
            manifest_file.write_text(json.dumps(legacy_manifest), encoding="utf-8")

            _, result, _ = manage_upstream.write_candidate(
                candidate_root=candidate_root,
                extracted_snapshot=archive_snapshot,
                archive_file=archive_file,
                archive_url=archive_url,
                base_manifest=manifest,
                candidate_index=candidate_index,
                checked_at=dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc),
            )

            self.assertEqual("candidate_exists", result)
            migrated = json.loads(manifest_file.read_text(encoding="utf-8"))
            migrated_archive = migrated["candidate_snapshot"]["archive"]
            self.assertNotIn("downloaded_at", migrated_archive)
            self.assertEqual("automatic", migrated_archive["acquisition_method"])
            self.assertEqual(archive_url, migrated_archive["source_url"])

    def test_promotion_rejects_a_snapshot_not_matching_the_archive(self) -> None:
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
            manifest_file.write_text(json.dumps(source_manifest), encoding="utf-8")
            contract_file = references / "update-contract.json"
            shutil.copy2(source_references / "update-contract.json", contract_file)
            state_file = references / "update-status.json"
            state_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "active_snapshot_id": active["id"],
                        "pending_candidate_ids": [],
                    }
                ),
                encoding="utf-8",
            )
            archive_file = root / "candidate.zip"
            with zipfile.ZipFile(archive_file, "w") as archive:
                for source_file in sorted(source_snapshot.rglob("*.md")):
                    relative_path = source_file.relative_to(source_snapshot)
                    archive.write(
                        source_file,
                        (Path("snapshot") / relative_path).as_posix(),
                    )
            manifest_for_candidate = dict(source_manifest)
            manifest_for_candidate["_manifest_dir"] = references
            candidate_root = references / "candidates"
            candidate_id, _, _ = manage_upstream.write_candidate(
                candidate_root=candidate_root,
                extracted_snapshot=source_snapshot,
                archive_file=archive_file,
                archive_url=(
                    "https://design.digital.go.jp/dads/dads-markdown-20260901.zip"
                ),
                base_manifest=manifest_for_candidate,
                candidate_index=source_index,
                checked_at=dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc),
            )
            candidate_snapshot = candidate_root / candidate_id / "snapshot/index.md"
            candidate_snapshot.write_text(
                candidate_snapshot.read_text(encoding="utf-8") + "\ntampered\n",
                encoding="utf-8",
            )

            arguments = argparse.Namespace(
                human_approved=True,
                candidate_id=candidate_id,
                state_file=state_file,
                contract_file=contract_file,
                manifest_file=manifest_file,
                candidate_root=candidate_root,
                upstream_root=references / "upstream",
            )
            with self.assertRaises(manage_upstream.UpstreamError):
                manage_upstream.promote_candidate(arguments)


if __name__ == "__main__":
    unittest.main()
