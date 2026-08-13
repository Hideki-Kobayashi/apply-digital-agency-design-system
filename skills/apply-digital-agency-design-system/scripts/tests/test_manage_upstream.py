from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from email.message import Message
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
            mock.patch.object(manage_upstream, "resolve_link_parser") as network,
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
            mock.patch.object(manage_upstream, "resolve_link_parser") as network,
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

    def test_check_uses_automatic_link_parser_selection_by_default(self) -> None:
        arguments = manage_upstream.build_parser().parse_args(
            ["check", "--network-approved"]
        )
        self.assertEqual("auto", arguments.link_parser)


class LinkParserTests(unittest.TestCase):
    @staticmethod
    def policy() -> manage_upstream.SourcePolicy:
        return manage_upstream.source_policy(
            {
                "allowed_hosts": ["design.digital.go.jp"],
                "allowed_path_prefixes": ["/dads/"],
                "archive_path_pattern": (r"^/dads/dads-markdown-[0-9]{8}\.zip$"),
                "archive_content_types": ["application/zip"],
            }
        )

    def test_auto_prefers_ax_when_available(self) -> None:
        with mock.patch.object(manage_upstream.shutil, "which", return_value="/bin/ax"):
            self.assertEqual("ax", manage_upstream.resolve_link_parser("auto"))

    def test_auto_falls_back_to_standard_library(self) -> None:
        with mock.patch.object(manage_upstream.shutil, "which", return_value=None):
            self.assertEqual("stdlib", manage_upstream.resolve_link_parser("auto"))

    def test_explicit_ax_requires_the_command(self) -> None:
        with (
            mock.patch.object(manage_upstream.shutil, "which", return_value=None),
            self.assertRaises(manage_upstream.UpstreamError),
        ):
            manage_upstream.resolve_link_parser("ax")

    def test_standard_library_extracts_the_unique_official_archive(self) -> None:
        urls = manage_upstream.archive_urls_from_html(
            """
            <a href="/dads/other.zip">other</a>
            <a href="/dads/dads-markdown-20260805.zip">Markdown</a>
            """,
            "dads-markdown-",
            ".zip",
            "https://design.digital.go.jp/dads/resources/",
            self.policy(),
        )
        self.assertEqual(
            ["https://design.digital.go.jp/dads/dads-markdown-20260805.zip"],
            urls,
        )

    def test_standard_library_rejects_matching_links_to_other_hosts(self) -> None:
        with self.assertRaises(manage_upstream.UpstreamError):
            manage_upstream.archive_urls_from_html(
                '<a href="https://example.com/dads-markdown-20260805.zip">ZIP</a>',
                "dads-markdown-",
                ".zip",
                "https://design.digital.go.jp/dads/resources/",
                self.policy(),
            )

    def test_ax_link_parser_deduplicates_identical_links(self) -> None:
        rows = [
            {"href": "/dads/dads-markdown-20260805.zip"},
            {"href": "/dads/dads-markdown-20260805.zip"},
        ]
        with mock.patch.object(manage_upstream, "run_ax_json", return_value=rows):
            urls = manage_upstream.archive_urls_with_ax(
                "<html></html>",
                {"href_contains": "dads-markdown-", "href_suffix": ".zip"},
                "https://design.digital.go.jp/dads/resources/",
                self.policy(),
            )
        self.assertEqual(
            ["https://design.digital.go.jp/dads/dads-markdown-20260805.zip"],
            urls,
        )

    def test_ax_receives_utf8_and_extracts_all_links(self) -> None:
        completed = mock.Mock(returncode=0, stdout="[]", stderr="")
        with (
            mock.patch.object(
                manage_upstream.shutil, "which", return_value="/usr/local/bin/ax"
            ),
            mock.patch.object(
                manage_upstream.subprocess, "run", return_value=completed
            ) as run,
        ):
            manage_upstream.run_ax_json(["-", "a", "--all"], "案内🙂")

        run.assert_called_once_with(
            ["/usr/local/bin/ax", "-", "a", "--all"],
            check=False,
            capture_output=True,
            input="案内🙂",
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=manage_upstream.NETWORK_TIMEOUT_SECONDS,
        )

    def test_ax_archive_parser_requests_every_matching_link(self) -> None:
        with mock.patch.object(manage_upstream, "run_ax_json", return_value=[]) as run:
            manage_upstream.archive_urls_with_ax(
                "<html></html>",
                {"href_contains": "dads-markdown-", "href_suffix": ".zip"},
                "https://design.digital.go.jp/dads/resources/",
                self.policy(),
            )

        self.assertIn("--all", run.call_args.args[0])

    def test_archive_discovery_uses_standard_library_parser(self) -> None:
        headers = Message()
        headers["Content-Type"] = "text/html; charset=utf-8"
        response = mock.Mock()
        response.headers = headers
        response.geturl.return_value = "https://design.digital.go.jp/dads/resources/"
        response.read.side_effect = [
            b'<a href="/dads/dads-markdown-20260805.zip">Markdown</a>',
            b"",
        ]
        context = mock.MagicMock()
        context.__enter__.return_value = response
        contract = {
            "sources": {
                "resources_page": {
                    "url": "https://design.digital.go.jp/dads/resources/",
                    "archive_link": {
                        "href_contains": "dads-markdown-",
                        "href_suffix": ".zip",
                    },
                }
            }
        }

        with mock.patch.object(
            manage_upstream, "open_source_response", return_value=context
        ):
            archive_url, validator = manage_upstream.find_current_archive(
                contract,
                self.policy(),
                "stdlib",
            )

        self.assertEqual(
            "https://design.digital.go.jp/dads/dads-markdown-20260805.zip",
            archive_url,
        )
        self.assertEqual(
            "https://design.digital.go.jp/dads/resources/", validator["url"]
        )

    def test_ax_failure_does_not_retry_with_standard_library(self) -> None:
        with (
            mock.patch.object(
                manage_upstream,
                "run_ax_json",
                side_effect=manage_upstream.UpstreamError("ax failed"),
            ),
            mock.patch.object(
                manage_upstream, "archive_urls_from_html"
            ) as standard_library,
            self.assertRaisesRegex(manage_upstream.UpstreamError, "ax failed"),
        ):
            manage_upstream.archive_urls_with_ax(
                '<a href="/dads/dads-markdown-20260805.zip">Markdown</a>',
                {"href_contains": "dads-markdown-", "href_suffix": ".zip"},
                "https://design.digital.go.jp/dads/resources/",
                self.policy(),
            )
        standard_library.assert_not_called()


class SourceTransportTests(unittest.TestCase):
    @staticmethod
    def policy() -> manage_upstream.SourcePolicy:
        return LinkParserTests.policy()

    @staticmethod
    def zip_bytes() -> bytes:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as bundle:
            bundle.writestr("README.md", "fixture")
            bundle.writestr("index.md", "# fixture")
        return output.getvalue()

    @staticmethod
    def response(payload: bytes, declared_length: int | None = None) -> mock.Mock:
        headers = Message()
        headers["Content-Type"] = "application/zip"
        if declared_length is not None:
            headers["Content-Length"] = str(declared_length)
        response = mock.Mock()
        response.headers = headers
        response.geturl.return_value = (
            "https://design.digital.go.jp/dads/dads-markdown-20260805.zip"
        )
        response.read.side_effect = [payload, b""]
        return response

    def test_url_policy_rejects_non_archive_paths(self) -> None:
        with self.assertRaises(manage_upstream.UpstreamError):
            manage_upstream.ensure_allowed_url(
                "https://design.digital.go.jp/dads/other.zip",
                self.policy(),
                require_archive=True,
            )

    def test_url_policy_rejects_query_and_fragment(self) -> None:
        for suffix in ("?download=1", "#archive"):
            with (
                self.subTest(suffix=suffix),
                self.assertRaises(manage_upstream.UpstreamError),
            ):
                manage_upstream.ensure_allowed_url(
                    "https://design.digital.go.jp/"
                    f"dads/dads-markdown-20260805.zip{suffix}",
                    self.policy(),
                    require_archive=True,
                )

    def test_redirect_rejects_http_and_other_hosts_before_following(self) -> None:
        handler = manage_upstream.AllowedRedirectHandler(self.policy(), False)
        request = manage_upstream.Request(
            "https://design.digital.go.jp/dads/resources/"
        )
        for redirect_url in (
            "http://design.digital.go.jp/dads/resources/",
            "https://example.com/dads/resources/",
        ):
            with (
                self.subTest(url=redirect_url),
                self.assertRaises(manage_upstream.UpstreamError),
            ):
                handler.redirect_request(
                    request,
                    None,
                    302,
                    "Found",
                    Message(),
                    redirect_url,
                )

    def test_head_method_is_preserved_after_allowed_redirect(self) -> None:
        handler = manage_upstream.AllowedRedirectHandler(self.policy(), False)
        request = manage_upstream.Request(
            "https://design.digital.go.jp/dads/feed.xml",
            method="HEAD",
        )
        redirected = handler.redirect_request(
            request,
            None,
            302,
            "Found",
            Message(),
            "https://design.digital.go.jp/dads/feed-latest.xml",
        )
        self.assertIsNotNone(redirected)
        self.assertEqual("HEAD", redirected.get_method())

    def test_transport_uses_tls12_and_disables_environment_proxy(self) -> None:
        headers = Message()
        headers["Content-Type"] = "text/html"
        response = mock.Mock(status=200)
        response.headers = headers
        response.geturl.return_value = "https://design.digital.go.jp/dads/resources/"
        opener = mock.Mock()
        opener.open.return_value = response
        tls_context = mock.Mock()

        with (
            mock.patch.object(
                manage_upstream.ssl,
                "create_default_context",
                return_value=tls_context,
            ),
            mock.patch.object(
                manage_upstream, "build_opener", return_value=opener
            ) as build_opener,
            manage_upstream.open_source_response(
                "https://design.digital.go.jp/dads/resources/",
                self.policy(),
                allowed_content_types=frozenset({"text/html"}),
            ),
        ):
            pass

        self.assertEqual(
            manage_upstream.ssl.TLSVersion.TLSv1_2,
            tls_context.minimum_version,
        )
        handlers = build_opener.call_args.args
        proxy_handler = next(
            handler
            for handler in handlers
            if isinstance(handler, manage_upstream.ProxyHandler)
        )
        https_handler = next(
            handler
            for handler in handlers
            if isinstance(handler, manage_upstream.HTTPSHandler)
        )
        self.assertEqual({}, proxy_handler.proxies)
        self.assertIs(tls_context, https_handler._context)
        response.close.assert_called_once()

    def test_download_is_atomic_and_records_get_validator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "archive.zip"
            payload = self.zip_bytes()
            response = self.response(payload, len(payload))
            context = mock.MagicMock()
            context.__enter__.return_value = response
            with mock.patch.object(
                manage_upstream, "open_source_response", return_value=context
            ):
                validator = manage_upstream.download_archive(
                    "https://design.digital.go.jp/dads/dads-markdown-20260805.zip",
                    destination,
                    self.policy(),
                )
            self.assertEqual(payload, destination.read_bytes())
            self.assertEqual("application/zip", validator["content_type"])

    def test_download_rejects_oversized_response_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "archive.zip"
            response = self.response(b"", manage_upstream.MAX_ARCHIVE_BYTES + 1)
            context = mock.MagicMock()
            context.__enter__.return_value = response
            with (
                mock.patch.object(
                    manage_upstream, "open_source_response", return_value=context
                ),
                self.assertRaises(manage_upstream.UpstreamError),
            ):
                manage_upstream.download_archive(
                    "https://design.digital.go.jp/dads/dads-markdown-20260805.zip",
                    destination,
                    self.policy(),
                )
            self.assertFalse(destination.exists())

    def test_download_rejects_stream_over_limit_without_content_length(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "archive.zip"
            destination.write_bytes(b"existing")
            response = self.response(b"")
            response.read.side_effect = [b"1234", b"56", b""]
            context = mock.MagicMock()
            context.__enter__.return_value = response
            with (
                mock.patch.object(
                    manage_upstream, "open_source_response", return_value=context
                ),
                mock.patch.object(manage_upstream, "MAX_ARCHIVE_BYTES", 5),
                self.assertRaises(manage_upstream.UpstreamError),
            ):
                manage_upstream.download_archive(
                    "https://design.digital.go.jp/dads/dads-markdown-20260805.zip",
                    destination,
                    self.policy(),
                )
            self.assertEqual(b"existing", destination.read_bytes())
            self.assertEqual([destination], list(root.iterdir()))

    def test_download_rejects_non_zip_without_replacing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "archive.zip"
            destination.write_bytes(b"existing")
            response = self.response(b"not a zip")
            context = mock.MagicMock()
            context.__enter__.return_value = response
            with (
                mock.patch.object(
                    manage_upstream, "open_source_response", return_value=context
                ),
                self.assertRaises(manage_upstream.UpstreamError),
            ):
                manage_upstream.download_archive(
                    "https://design.digital.go.jp/dads/dads-markdown-20260805.zip",
                    destination,
                    self.policy(),
                )
            self.assertEqual(b"existing", destination.read_bytes())


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
