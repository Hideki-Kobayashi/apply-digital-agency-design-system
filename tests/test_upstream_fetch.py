from __future__ import annotations

import io
import subprocess
import sys
import tempfile
import unittest
import zipfile
from email.message import Message
from pathlib import Path
from unittest import mock
from urllib.request import HTTPSHandler, ProxyHandler, Request

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPOSITORY_ROOT / "skills/apply-digital-agency-design-system"
SCRIPTS_DIR = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import upstream_fetch

RESOURCE_URL = "https://design.digital.go.jp/dads/resources/"
ARCHIVE_URL = "https://design.digital.go.jp/dads/dads-markdown-20260805.zip"


def contract_fixture() -> dict:
    return {
        "allowed_hosts": ["design.digital.go.jp"],
        "allowed_path_prefixes": ["/dads/"],
        "archive_path_pattern": r"^/dads/dads-markdown-[0-9]{8}\.zip$",
        "sources": {
            "resources_page": {
                "url": RESOURCE_URL,
                "archive_link": {
                    "href_contains": "dads-markdown-",
                    "href_suffix": ".zip",
                },
            }
        },
    }


def zip_bytes() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as bundle:
        bundle.writestr("README.md", "fixture")
        bundle.writestr("index.md", "# fixture")
    return output.getvalue()


class FakeResponse(io.BytesIO):
    def __init__(
        self,
        body: bytes,
        url: str,
        content_type: str,
        content_length: int | None = None,
        content_encoding: str | None = None,
    ) -> None:
        super().__init__(body)
        self.status = 200
        self.final_url = url
        self.read_count = 0
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)
        if content_encoding is not None:
            self.headers["Content-Encoding"] = content_encoding

    def geturl(self) -> str:
        return self.final_url

    def read(self, size: int = -1) -> bytes:
        self.read_count += 1
        return super().read(size)


class FakeOpener:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.requests: list[tuple[Request, int]] = []

    def open(self, request: Request, timeout: int) -> FakeResponse:
        self.requests.append((request, timeout))
        return self.response


class ExplodingResponse(FakeResponse):
    def __init__(self, first_chunk: bytes) -> None:
        super().__init__(first_chunk, ARCHIVE_URL, "application/zip")

    def read(self, size: int = -1) -> bytes:
        self.read_count += 1
        if self.read_count > 1:
            raise OSError("stream stopped")
        return io.BytesIO.read(self, size)


class BackendSelectionTests(unittest.TestCase):
    def test_auto_prefers_ax_for_the_entire_check(self) -> None:
        with mock.patch.object(
            upstream_fetch.shutil, "which", return_value="/usr/local/bin/ax"
        ):
            backend = upstream_fetch.select_fetch_backend("auto", contract_fixture())
        self.assertIsInstance(backend, upstream_fetch.AxBackend)
        self.assertEqual("ax", backend.name)

    def test_auto_uses_stdlib_when_ax_is_missing(self) -> None:
        with mock.patch.object(upstream_fetch.shutil, "which", return_value=None):
            backend = upstream_fetch.select_fetch_backend("auto", contract_fixture())
        self.assertIsInstance(backend, upstream_fetch.StdlibBackend)
        self.assertEqual("stdlib", backend.name)

    def test_explicit_ax_requires_ax(self) -> None:
        with (
            mock.patch.object(upstream_fetch.shutil, "which", return_value=None),
            self.assertRaises(upstream_fetch.UpstreamError),
        ):
            upstream_fetch.select_fetch_backend("ax", contract_fixture())

    def test_explicit_stdlib_does_not_depend_on_ax(self) -> None:
        with mock.patch.object(
            upstream_fetch.shutil, "which", return_value="/usr/local/bin/ax"
        ):
            backend = upstream_fetch.select_fetch_backend("stdlib", contract_fixture())
        self.assertIsInstance(backend, upstream_fetch.StdlibBackend)


class UrlPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = upstream_fetch.build_source_policy(contract_fixture())

    def test_archive_url_must_match_the_official_pattern(self) -> None:
        with self.assertRaises(upstream_fetch.UpstreamError):
            upstream_fetch.ensure_allowed_url(
                "https://design.digital.go.jp/dads/other.zip",
                self.policy,
                require_archive=True,
            )

    def test_url_rejects_every_value_outside_the_contract(self) -> None:
        invalid_urls = (
            "http://design.digital.go.jp/dads/resources/",
            "https://example.com/dads/resources/",
            "https://user@design.digital.go.jp/dads/resources/",
            "https://design.digital.go.jp:444/dads/resources/",
            "https://design.digital.go.jp/other/resources/",
            "https://design.digital.go.jp/dads/resources/?download=1",
            "https://design.digital.go.jp/dads/resources/#latest",
            "https://design.digital.go.jp/dads/resources/\n",
        )
        for url in invalid_urls:
            with (
                self.subTest(url=url),
                self.assertRaises(upstream_fetch.UpstreamError),
            ):
                upstream_fetch.ensure_allowed_url(url, self.policy)

    def test_redirect_handler_rejects_a_redirect_before_following_it(self) -> None:
        handler = upstream_fetch.AllowedRedirectHandler(self.policy, False)
        with self.assertRaises(upstream_fetch.UpstreamError):
            handler.redirect_request(
                Request(RESOURCE_URL),
                None,
                302,
                "Found",
                Message(),
                "https://example.com/dads/resources/",
            )

    def test_redirect_handler_allows_an_official_redirect(self) -> None:
        handler = upstream_fetch.AllowedRedirectHandler(self.policy, False)
        redirected = handler.redirect_request(
            Request(RESOURCE_URL),
            None,
            302,
            "Found",
            Message(),
            "https://design.digital.go.jp/dads/resources/latest/",
        )
        self.assertEqual(
            "https://design.digital.go.jp/dads/resources/latest/",
            redirected.full_url,
        )

    def test_archive_resolution_rejects_a_matching_external_link(self) -> None:
        with self.assertRaises(upstream_fetch.UpstreamError):
            upstream_fetch.resolve_archive_urls(
                ["https://example.com/dads/dads-markdown-20260805.zip"],
                contract_fixture()["sources"]["resources_page"]["archive_link"],
                RESOURCE_URL,
                self.policy,
            )


class AxBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = upstream_fetch.build_source_policy(contract_fixture())
        self.backend = upstream_fetch.AxBackend(self.policy, "/usr/local/bin/ax")

    def test_ax_owns_page_fetch_and_html_extraction(self) -> None:
        calls: list[list[str]] = []

        def fake_ax(_executable: str, arguments: list[str]) -> object:
            calls.append(arguments)
            if arguments[0] == RESOURCE_URL:
                output_path = Path(arguments[arguments.index("-o") + 1])
                self.assertTrue(output_path.exists())
                body = b"<html>resource</html>"
                output_path.write_bytes(body)
                return {
                    "status": 200,
                    "ok": True,
                    "url": RESOURCE_URL,
                    "saved": str(output_path),
                    "bytes": len(body),
                }
            self.assertTrue(Path(arguments[0]).is_file())
            return [
                {"href": "/dads/dads-markdown-20260805.zip"},
                {"href": "/dads/dads-markdown-20260805.zip"},
            ]

        with (
            mock.patch.object(upstream_fetch, "run_ax_json", side_effect=fake_ax),
            mock.patch.object(upstream_fetch, "build_opener") as stdlib_network,
        ):
            archive_url = self.backend.find_current_archive(contract_fixture())

        self.assertEqual(ARCHIVE_URL, archive_url)
        self.assertEqual(2, len(calls))
        self.assertEqual(RESOURCE_URL, calls[0][0])
        self.assertIn("-o", calls[0])
        self.assertIn("--max-bytes", calls[0])
        self.assertEqual('a[href*="dads-markdown-"][href$=".zip"]', calls[1][1])
        self.assertIn("--all", calls[1])
        self.assertIn("--no-cache", calls[1])
        stdlib_network.assert_not_called()

    def test_ax_rejects_an_unreported_final_url_before_parsing(self) -> None:
        response = {
            "status": 200,
            "ok": True,
            "saved": "/tmp/missing",
            "bytes": 0,
        }
        with (
            mock.patch.object(
                upstream_fetch, "run_ax_json", return_value=response
            ) as run,
            self.assertRaisesRegex(
                upstream_fetch.UpstreamError, "\u6700\u7d42\u53d6\u5f97\u5148URL"
            ),
        ):
            self.backend.find_current_archive(contract_fixture())
        run.assert_called_once()

    def test_ax_rejects_a_redirect_outside_the_official_host(self) -> None:
        def fake_ax(_executable: str, arguments: list[str]) -> dict:
            output_path = Path(arguments[arguments.index("-o") + 1])
            output_path.write_bytes(b"redirected")
            return {
                "status": 200,
                "ok": True,
                "url": "https://example.com/dads/resources/",
                "saved": str(output_path),
                "bytes": 10,
            }

        with (
            mock.patch.object(
                upstream_fetch, "run_ax_json", side_effect=fake_ax
            ) as run,
            self.assertRaises(upstream_fetch.UpstreamError),
        ):
            self.backend.find_current_archive(contract_fixture())
        run.assert_called_once()

    def test_ax_downloads_the_archive_without_stdlib_network(self) -> None:
        payload = zip_bytes()

        def fake_ax(_executable: str, arguments: list[str]) -> dict:
            output_path = Path(arguments[arguments.index("-o") + 1])
            self.assertTrue(output_path.exists())
            output_path.write_bytes(payload)
            return {
                "status": 200,
                "ok": True,
                "url": ARCHIVE_URL,
                "saved": str(output_path),
                "bytes": len(payload),
            }

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "archive.zip"
            with (
                mock.patch.object(
                    upstream_fetch, "run_ax_json", side_effect=fake_ax
                ) as run,
                mock.patch.object(upstream_fetch, "build_opener") as stdlib_network,
            ):
                result = self.backend.download_archive(ARCHIVE_URL, destination)
            self.assertEqual(payload, destination.read_bytes())
            self.assertEqual(len(payload), result["bytes"])
            arguments = run.call_args.args[1]
            self.assertIn("-o", arguments)
            self.assertIn("--max-bytes", arguments)
            stdlib_network.assert_not_called()

    def test_ax_failure_does_not_switch_to_stdlib(self) -> None:
        with (
            mock.patch.object(
                upstream_fetch,
                "run_ax_json",
                side_effect=upstream_fetch.UpstreamError("ax failed"),
            ),
            mock.patch.object(upstream_fetch, "build_opener") as stdlib_network,
            self.assertRaisesRegex(upstream_fetch.UpstreamError, "ax failed"),
        ):
            self.backend.find_current_archive(contract_fixture())
        stdlib_network.assert_not_called()

    def test_ax_rejects_non_zip_and_preserves_existing_destination(self) -> None:
        payload = b"not a zip"

        def fake_ax(_executable: str, arguments: list[str]) -> dict:
            output_path = Path(arguments[arguments.index("-o") + 1])
            output_path.write_bytes(payload)
            return {
                "status": 200,
                "ok": True,
                "url": ARCHIVE_URL,
                "saved": str(output_path),
                "bytes": len(payload),
            }

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "archive.zip"
            destination.write_bytes(b"existing")
            with (
                mock.patch.object(upstream_fetch, "run_ax_json", side_effect=fake_ax),
                self.assertRaisesRegex(upstream_fetch.UpstreamError, "ZIP"),
            ):
                self.backend.download_archive(ARCHIVE_URL, destination)
            self.assertEqual(b"existing", destination.read_bytes())

    def test_ax_rejects_a_reported_size_larger_than_the_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            saved_path = Path(temporary) / "download"
            saved_path.write_bytes(b"")
            response = {
                "status": 200,
                "ok": True,
                "url": ARCHIVE_URL,
                "saved": str(saved_path),
                "bytes": 6,
            }
            with self.assertRaises(upstream_fetch.UpstreamError):
                upstream_fetch.validate_ax_download(
                    response,
                    ARCHIVE_URL,
                    saved_path,
                    self.policy,
                    max_bytes=5,
                    require_archive=True,
                )

    def test_ax_subprocess_uses_utf8_and_a_process_timeout(self) -> None:
        completed = mock.Mock(returncode=0, stdout="{}", stderr="")
        with mock.patch.object(
            upstream_fetch.subprocess, "run", return_value=completed
        ) as run:
            upstream_fetch.run_ax_json("/usr/local/bin/ax", ["--help"])
        self.assertEqual("utf-8", run.call_args.kwargs["encoding"])
        self.assertEqual("strict", run.call_args.kwargs["errors"])
        self.assertEqual(
            upstream_fetch.AX_PROCESS_TIMEOUT_SECONDS,
            run.call_args.kwargs["timeout"],
        )

    def test_ax_subprocess_timeout_is_reported(self) -> None:
        with (
            mock.patch.object(
                upstream_fetch.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired("ax", 1),
            ),
            self.assertRaises(upstream_fetch.UpstreamError),
        ):
            upstream_fetch.run_ax_json("/usr/local/bin/ax", [RESOURCE_URL])

    def test_ax_malformed_json_is_rejected(self) -> None:
        completed = mock.Mock(returncode=0, stdout="not json", stderr="")
        with (
            mock.patch.object(upstream_fetch.subprocess, "run", return_value=completed),
            self.assertRaises(upstream_fetch.UpstreamError),
        ):
            upstream_fetch.run_ax_json("/usr/local/bin/ax", [RESOURCE_URL])


class StdlibBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = upstream_fetch.build_source_policy(contract_fixture())
        self.backend = upstream_fetch.StdlibBackend(self.policy)

    def test_stdlib_fetches_and_parses_the_resource_page_without_ax(self) -> None:
        body = b'<a href="/dads/dads-markdown-20260805.zip">Markdown</a>'
        response = FakeResponse(
            body,
            RESOURCE_URL,
            "text/html; charset=utf-8",
            len(body),
        )
        opener = FakeOpener(response)
        with (
            mock.patch.object(
                upstream_fetch, "build_opener", return_value=opener
            ) as build,
            mock.patch.object(upstream_fetch, "run_ax_json") as ax,
        ):
            archive_url = self.backend.find_current_archive(contract_fixture())

        self.assertEqual(ARCHIVE_URL, archive_url)
        ax.assert_not_called()
        handlers = build.call_args.args
        proxy = next(
            handler for handler in handlers if isinstance(handler, ProxyHandler)
        )
        self.assertEqual({}, proxy.proxies)
        self.assertTrue(any(isinstance(handler, HTTPSHandler) for handler in handlers))
        self.assertTrue(
            any(
                isinstance(handler, upstream_fetch.AllowedRedirectHandler)
                for handler in handlers
            )
        )

    def test_stdlib_downloads_and_validates_the_archive(self) -> None:
        payload = zip_bytes()
        response = FakeResponse(
            payload,
            ARCHIVE_URL,
            "application/zip",
            len(payload),
        )
        opener = FakeOpener(response)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "archive.zip"
            with mock.patch.object(upstream_fetch, "build_opener", return_value=opener):
                result = self.backend.download_archive(ARCHIVE_URL, destination)
            self.assertEqual(payload, destination.read_bytes())
            self.assertEqual(len(payload), result["bytes"])

    def test_stdlib_rejects_a_stream_over_the_limit(self) -> None:
        response = FakeResponse(b"123456", ARCHIVE_URL, "application/zip")
        opener = FakeOpener(response)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "archive.zip"
            destination.write_bytes(b"existing")
            with (
                mock.patch.object(upstream_fetch, "build_opener", return_value=opener),
                mock.patch.object(upstream_fetch, "MAX_ARCHIVE_BYTES", 5),
                self.assertRaises(upstream_fetch.UpstreamError),
            ):
                self.backend.download_archive(ARCHIVE_URL, destination)
            self.assertEqual(b"existing", destination.read_bytes())

    def test_stdlib_rejects_declared_oversize_before_reading(self) -> None:
        response = FakeResponse(
            b"small",
            ARCHIVE_URL,
            "application/zip",
            upstream_fetch.MAX_ARCHIVE_BYTES + 1,
        )
        opener = FakeOpener(response)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "archive.zip"
            destination.write_bytes(b"existing")
            with (
                mock.patch.object(upstream_fetch, "build_opener", return_value=opener),
                self.assertRaises(upstream_fetch.UpstreamError),
            ):
                self.backend.download_archive(ARCHIVE_URL, destination)
            self.assertEqual(b"existing", destination.read_bytes())
            self.assertEqual(0, response.read_count)

    def test_stdlib_rejects_non_zip_without_replacing_destination(self) -> None:
        payload = b"not a zip"
        response = FakeResponse(
            payload,
            ARCHIVE_URL,
            "application/octet-stream",
            len(payload),
        )
        opener = FakeOpener(response)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "archive.zip"
            destination.write_bytes(b"existing")
            with (
                mock.patch.object(upstream_fetch, "build_opener", return_value=opener),
                self.assertRaisesRegex(upstream_fetch.UpstreamError, "ZIP"),
            ):
                self.backend.download_archive(ARCHIVE_URL, destination)
            self.assertEqual(b"existing", destination.read_bytes())

    def test_stdlib_stream_failure_preserves_existing_destination(self) -> None:
        opener = FakeOpener(ExplodingResponse(b"partial"))
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "archive.zip"
            destination.write_bytes(b"existing")
            with (
                mock.patch.object(upstream_fetch, "build_opener", return_value=opener),
                self.assertRaisesRegex(OSError, "stream stopped"),
            ):
                self.backend.download_archive(ARCHIVE_URL, destination)
            self.assertEqual(b"existing", destination.read_bytes())
            self.assertEqual([destination], list(Path(temporary).iterdir()))

    def test_stdlib_rejects_an_unexpected_page_content_type(self) -> None:
        response = FakeResponse(b"{}", RESOURCE_URL, "application/json")
        with (
            mock.patch.object(
                upstream_fetch,
                "build_opener",
                return_value=FakeOpener(response),
            ),
            self.assertRaisesRegex(upstream_fetch.UpstreamError, "Content-Type"),
        ):
            self.backend.find_current_archive(contract_fixture())

    def test_stdlib_rejects_an_unapproved_final_url(self) -> None:
        response = FakeResponse(
            b"<html></html>",
            "https://example.com/dads/resources/",
            "text/html",
        )
        with (
            mock.patch.object(
                upstream_fetch,
                "build_opener",
                return_value=FakeOpener(response),
            ),
            self.assertRaises(upstream_fetch.UpstreamError),
        ):
            self.backend.find_current_archive(contract_fixture())

    def test_stdlib_rejects_compressed_responses(self) -> None:
        response = FakeResponse(
            b"<html></html>",
            RESOURCE_URL,
            "text/html",
            content_encoding="gzip",
        )
        with (
            mock.patch.object(
                upstream_fetch,
                "build_opener",
                return_value=FakeOpener(response),
            ),
            self.assertRaisesRegex(upstream_fetch.UpstreamError, "HTTP応答"),
        ):
            self.backend.find_current_archive(contract_fixture())

    def test_stdlib_requires_tls_12_or_newer(self) -> None:
        self.assertGreaterEqual(
            self.backend.tls_context.minimum_version,
            upstream_fetch.ssl.TLSVersion.TLSv1_2,
        )


if __name__ == "__main__":
    unittest.main()
