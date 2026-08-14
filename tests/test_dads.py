from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = (
    REPOSITORY_ROOT / "skills" / "apply-digital-agency-design-system" / "scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))

import dads

ARCHIVE_URL = "https://design.digital.go.jp/dads/dads-markdown-20260805.zip"
LATEST_ARCHIVE_URL = "https://design.digital.go.jp/dads/dads-markdown-20260901.zip"
INSTALLED_AT = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)


def write_archive(path: Path, heading: str = "Button") -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("dads/README.md", "DADS")
        archive.writestr("dads/index.md", "# DADS")
        archive.writestr("dads/foundations/index.md", "# Foundations")
        archive.writestr("dads/components/index.md", "# Components")
        archive.writestr("dads/components/button/index.md", f"# {heading}")
        archive.writestr("dads/guidance/index.md", "# Guidance")


class DataRootTests(unittest.TestCase):
    def test_environment_override_has_priority(self) -> None:
        result = dads.resolve_data_root(
            environment={"DADS_SKILL_DATA_DIR": "/tmp/custom-dads"},
            platform_name="darwin",
            home=Path("/Users/example"),
        )
        self.assertEqual(Path("/tmp/custom-dads").resolve(), result)

    def test_defaults_are_os_specific(self) -> None:
        home = Path("/users/example")
        self.assertEqual(
            home / "Library" / "Application Support" / dads.SKILL_NAME,
            dads.resolve_data_root(environment={}, platform_name="darwin", home=home),
        )
        self.assertEqual(
            Path("C:/Local") / dads.SKILL_NAME,
            dads.resolve_data_root(
                environment={"LOCALAPPDATA": "C:/Local"},
                platform_name="win32",
                home=home,
            ),
        )
        self.assertEqual(
            home / ".local" / "share" / dads.SKILL_NAME,
            dads.resolve_data_root(environment={}, platform_name="linux", home=home),
        )


class UrlTests(unittest.TestCase):
    def test_only_official_versioned_zip_url_is_allowed(self) -> None:
        self.assertEqual(ARCHIVE_URL, dads.validate_archive_url(ARCHIVE_URL))
        invalid = (
            "http://design.digital.go.jp/dads/dads-markdown-20260805.zip",
            "https://example.com/dads/dads-markdown-20260805.zip",
            "https://design.digital.go.jp/dads/other.zip",
            f"{ARCHIVE_URL}?download=1",
        )
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(dads.DadsError):
                dads.validate_archive_url(url)


class InstallTests(unittest.TestCase):
    def test_manual_archive_installs_and_status_reads_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "dads-markdown-20260805.zip"
            data_root = root / "data"
            write_archive(archive)
            result = dads.install_data(
                data_root,
                archive_file=archive,
                now=INSTALLED_AT,
            )
            status = dads.read_status(data_root, now=INSTALLED_AT)

            self.assertTrue(result["installed"])
            self.assertEqual(
                "# Button",
                (data_root / "current/components/button/index.md").read_text(),
            )
            self.assertTrue(status["installed"])
            self.assertEqual(ARCHIVE_URL, status["source_url"])
            self.assertEqual("2026-08-05T12:00:00Z", status["checked_at"])
            self.assertFalse(status["check_due"])
            self.assertFalse(status["update_available"])
            self.assertTrue((data_root / "current/.dads-state.json").is_file())

    def test_replace_must_be_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "dads-markdown-20260805.zip"
            second = root / "dads-markdown-20260901.zip"
            data_root = root / "data"
            write_archive(first, "Old")
            write_archive(second, "New")
            dads.install_data(data_root, archive_file=first)

            with self.assertRaisesRegex(dads.DadsError, "--replace"):
                dads.install_data(data_root, archive_file=second)
            self.assertEqual(
                "# Old", (data_root / "current/components/button/index.md").read_text()
            )

            dads.install_data(data_root, archive_file=second, replace=True)
            self.assertEqual(
                "# New", (data_root / "current/components/button/index.md").read_text()
            )

    def test_replace_does_not_delete_an_unrelated_current_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_root = root / "data"
            current = data_root / "current"
            current.mkdir(parents=True)
            marker = current / "keep.txt"
            marker.write_text("keep", encoding="utf-8")
            archive = root / "dads-markdown-20260805.zip"
            write_archive(archive)

            with self.assertRaisesRegex(dads.DadsError, "このSkill"):
                dads.install_data(data_root, archive_file=archive, replace=True)

            self.assertEqual("keep", marker.read_text(encoding="utf-8"))

    def test_unsafe_zip_does_not_replace_current(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_root = root / "data"
            original = root / "dads-markdown-20260701.zip"
            write_archive(original, "Keep")
            dads.install_data(data_root, archive_file=original)
            archive = root / "dads-markdown-20260805.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../escape.md", "bad")

            with self.assertRaisesRegex(dads.DadsError, "不正なパス"):
                dads.install_data(data_root, archive_file=archive, replace=True)

            self.assertEqual(
                "# Keep",
                (data_root / "current/components/button/index.md").read_text(),
            )
            self.assertFalse((root / "escape.md").exists())

    def test_archive_must_have_the_required_dads_structure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "dads-markdown-20260805.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("index.md", "# incomplete")

            with self.assertRaisesRegex(dads.DadsError, "ルートを特定"):
                dads.install_data(root / "data", archive_file=archive)

    def test_status_rejects_an_incomplete_current_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_root = Path(temporary) / "data"
            (data_root / "current").mkdir(parents=True)

            with self.assertRaisesRegex(dads.DadsError, "構造が不完全"):
                dads.read_status(data_root)

    def test_network_install_requires_approval_before_running_ax(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_root = Path(temporary) / "data"
            with (
                mock.patch.object(dads.subprocess, "run") as run,
                self.assertRaisesRegex(dads.DadsError, "--network-approved"),
            ):
                dads.install_data(data_root, archive_url=ARCHIVE_URL)
            run.assert_not_called()
            self.assertFalse(data_root.exists())

    def test_ax_failure_returns_the_url_and_manual_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_root = Path(temporary) / "data"
            with (
                mock.patch.object(dads.shutil, "which", return_value=None),
                self.assertRaises(dads.DadsError) as raised,
            ):
                dads.install_data(
                    data_root,
                    archive_url=ARCHIVE_URL,
                    network_approved=True,
                )
            message = str(raised.exception)
            self.assertIn(ARCHIVE_URL, message)
            self.assertIn("--archive-file", message)

    def test_network_install_uses_ax_to_create_the_temporary_zip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.zip"
            data_root = root / "data"
            write_archive(source)
            calls: list[list[str]] = []

            def fake_run(
                command: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
                calls.append(command)
                destination = Path(command[command.index("-o") + 1])
                shutil.copy2(source, destination)
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                mock.patch.object(dads.shutil, "which", return_value="/usr/bin/ax"),
                mock.patch.object(dads.subprocess, "run", side_effect=fake_run),
            ):
                dads.install_data(
                    data_root,
                    archive_url=ARCHIVE_URL,
                    network_approved=True,
                )

            self.assertEqual("/usr/bin/ax", calls[0][0])
            self.assertEqual(ARCHIVE_URL, calls[0][1])
            self.assertIn("--max-bytes", calls[0])
            self.assertTrue((data_root / "current/index.md").is_file())


class UpdateCheckTests(unittest.TestCase):
    def install_current(self, root: Path) -> Path:
        archive = root / "dads-markdown-20260805.zip"
        data_root = root / "data"
        write_archive(archive)
        dads.install_data(data_root, archive_file=archive, now=INSTALLED_AT)
        return data_root

    def check_with_ax(
        self, data_root: Path, latest_url: str, *, now: datetime
    ) -> dict[str, object]:
        relative_url = latest_url.removeprefix("https://design.digital.go.jp")
        completed = subprocess.CompletedProcess(
            ["ax"], 0, json.dumps([{"url": relative_url}]), ""
        )
        with (
            mock.patch.object(dads.shutil, "which", return_value="/usr/bin/ax"),
            mock.patch.object(dads.subprocess, "run", return_value=completed) as run,
        ):
            result = dads.check_update(data_root, now=now)
        command = run.call_args.args[0]
        self.assertEqual(dads.RESOURCES_URL, command[1])
        self.assertIn("--no-cache", command)
        return result

    def test_status_is_due_at_exactly_thirty_days(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_root = self.install_current(Path(temporary))

            with mock.patch.object(dads.subprocess, "run") as run:
                before = dads.read_status(
                    data_root,
                    now=INSTALLED_AT
                    + timedelta(days=29, hours=23, minutes=59, seconds=59),
                )
                boundary = dads.read_status(
                    data_root,
                    now=INSTALLED_AT + timedelta(days=30),
                )

            run.assert_not_called()
            self.assertFalse(before["check_due"])
            self.assertTrue(boundary["check_due"])

    def test_successful_unchanged_check_updates_checked_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_root = self.install_current(Path(temporary))
            checked_at = INSTALLED_AT + timedelta(days=30)

            result = self.check_with_ax(data_root, ARCHIVE_URL, now=checked_at)

            self.assertTrue(result["checked"])
            self.assertFalse(result["changed"])
            self.assertFalse(result["update_available"])
            self.assertFalse(result["check_due"])
            self.assertEqual("2026-09-04T12:00:00Z", result["checked_at"])

    def test_successful_check_reports_an_available_update(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_root = self.install_current(Path(temporary))

            result = self.check_with_ax(
                data_root,
                LATEST_ARCHIVE_URL,
                now=INSTALLED_AT + timedelta(days=30),
            )

            self.assertTrue(result["update_available"])
            self.assertTrue(result["changed"])
            self.assertFalse(result["check_due"])
            self.assertEqual(LATEST_ARCHIVE_URL, result["latest_url"])
            self.assertEqual(ARCHIVE_URL, result["source_url"])

    def test_failed_check_does_not_change_checked_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_root = self.install_current(Path(temporary))
            state_file = data_root / "current/.dads-state.json"
            before = state_file.read_text(encoding="utf-8")
            failures = (
                ("missing", None, None),
                (
                    "command failure",
                    "/usr/bin/ax",
                    subprocess.CompletedProcess(["ax"], 2, "", "network error"),
                ),
            )

            for label, executable, completed in failures:
                with (
                    self.subTest(label=label),
                    mock.patch.object(dads.shutil, "which", return_value=executable),
                    mock.patch.object(dads.subprocess, "run", return_value=completed),
                    self.assertRaises(dads.DadsError) as raised,
                ):
                    dads.check_update(
                        data_root,
                        now=INSTALLED_AT + timedelta(days=30),
                    )

                self.assertEqual(before, state_file.read_text(encoding="utf-8"))
                self.assertIn(dads.RESOURCES_URL, str(raised.exception))
                self.assertIn("check --archive-file", str(raised.exception))

    def test_manual_archive_can_record_the_check_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_root = self.install_current(root)
            downloaded = root / "dads-markdown-20260901.zip"
            downloaded.write_bytes(b"downloaded by the user")

            with mock.patch.object(dads.subprocess, "run") as run:
                result = dads.check_update(
                    data_root,
                    archive_file=downloaded,
                    now=INSTALLED_AT + timedelta(days=30),
                )

            run.assert_not_called()
            self.assertTrue(result["update_available"])
            self.assertEqual(LATEST_ARCHIVE_URL, result["latest_url"])

    def test_state_replace_failure_preserves_the_previous_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_root = self.install_current(root)
            current = data_root / "current"
            state_file = current / dads.STATE_FILE_NAME
            before_state = state_file.read_text(encoding="utf-8")
            before_entries = set(current.iterdir())
            downloaded = root / "dads-markdown-20260901.zip"
            downloaded.write_bytes(b"downloaded by the user")

            with (
                mock.patch.object(
                    dads.os, "replace", side_effect=OSError("replace failed")
                ),
                self.assertRaisesRegex(dads.DadsError, "保存できません"),
            ):
                dads.check_update(
                    data_root,
                    archive_file=downloaded,
                    now=INSTALLED_AT + timedelta(days=30),
                )

            self.assertEqual(before_state, state_file.read_text(encoding="utf-8"))
            self.assertEqual(before_entries, set(current.iterdir()))


if __name__ == "__main__":
    unittest.main()
