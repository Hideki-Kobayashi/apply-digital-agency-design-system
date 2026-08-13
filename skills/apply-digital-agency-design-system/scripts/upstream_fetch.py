"""Fetch DADS update sources with one backend per check."""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import ssl
import subprocess
import tempfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)

NETWORK_TIMEOUT_SECONDS = 60
AX_PROCESS_TIMEOUT_SECONDS = NETWORK_TIMEOUT_SECONDS + 15
MAX_PAGE_BYTES = 5 * 1024 * 1024
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
PAGE_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})
HTTP_USER_AGENT = (
    "apply-digital-agency-design-system update-check "
    "(+https://github.com/Hideki-Kobayashi/apply-digital-agency-design-system)"
)


class UpstreamError(RuntimeError):
    """Raised when an update operation cannot complete safely."""


@dataclass(frozen=True)
class SourcePolicy:
    allowed_hosts: frozenset[str]
    allowed_path_prefixes: tuple[str, ...]
    archive_path_pattern: re.Pattern[str]


class FetchBackend(Protocol):
    name: str

    def find_current_archive(self, contract: dict[str, Any]) -> str: ...

    def download_archive(self, url: str, destination: Path) -> dict[str, Any]: ...


class AnchorHrefParser(HTMLParser):
    """Collect anchor href values for the dependency-free fallback."""

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(
        self, tag: str, attributes: list[tuple[str, str | None]]
    ) -> None:
        if tag.casefold() != "a":
            return
        for name, value in attributes:
            if name.casefold() == "href" and value:
                self.hrefs.append(value)
                return


class AllowedRedirectHandler(HTTPRedirectHandler):
    """Reject fallback redirects that leave the official source policy."""

    max_redirections = 5

    def __init__(self, policy: SourcePolicy, require_archive: bool) -> None:
        super().__init__()
        self.policy = policy
        self.require_archive = require_archive

    def redirect_request(
        self,
        request: Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> Request | None:
        ensure_allowed_url(new_url, self.policy, self.require_archive)
        return super().redirect_request(
            request, file_pointer, code, message, headers, new_url
        )


def build_source_policy(contract: dict[str, Any]) -> SourcePolicy:
    try:
        policy = SourcePolicy(
            allowed_hosts=frozenset(contract["allowed_hosts"]),
            allowed_path_prefixes=tuple(contract["allowed_path_prefixes"]),
            archive_path_pattern=re.compile(contract["archive_path_pattern"]),
        )
    except (KeyError, TypeError, re.error) as error:
        raise UpstreamError(f"更新契約のURL方針を解析できません: {error}") from error
    if not policy.allowed_hosts or not policy.allowed_path_prefixes:
        raise UpstreamError("更新契約の許可先が空です")
    return policy


def ensure_allowed_url(
    url: str,
    policy: SourcePolicy,
    require_archive: bool = False,
) -> None:
    if any(ord(character) < 32 or ord(character) == 127 for character in url):
        raise UpstreamError("取得先URLに制御文字があります")
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError as error:
        raise UpstreamError(f"取得先URLを解析できません: {url}") from error

    if (
        parsed.scheme != "https"
        or parsed.hostname not in policy.allowed_hosts
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or not any(
            parsed.path.startswith(prefix) for prefix in policy.allowed_path_prefixes
        )
        or (
            require_archive
            and policy.archive_path_pattern.fullmatch(parsed.path) is None
        )
        or bool(parsed.query)
        or bool(parsed.fragment)
    ):
        raise UpstreamError(f"許可されていない取得先です: {url}")


def resolve_archive_urls(
    hrefs: list[str],
    link_rule: dict[str, str],
    base_url: str,
    policy: SourcePolicy,
) -> list[str]:
    contains = link_rule.get("href_contains")
    suffix = link_rule.get("href_suffix")
    if not contains or not suffix:
        raise UpstreamError("アーカイブのリンク条件が空です")

    urls: list[str] = []
    for href in hrefs:
        if contains not in href or not href.endswith(suffix):
            continue
        archive_url = urljoin(base_url, href)
        ensure_allowed_url(archive_url, policy, require_archive=True)
        if archive_url not in urls:
            urls.append(archive_url)
    return urls


def require_unique_archive_url(urls: list[str]) -> str:
    if len(urls) != 1:
        raise UpstreamError(f"Markdown ZIPのリンクを一意に取得できません: {urls!r}")
    return urls[0]


def run_ax_json(executable: str, arguments: list[str]) -> Any:
    try:
        completed = subprocess.run(
            [executable, *arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=AX_PROCESS_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise UpstreamError(f"axを実行できません: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise UpstreamError(f"axの実行に失敗しました: {detail}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise UpstreamError(f"axのJSON出力を解析できません: {error}") from error


def validate_ax_download(
    response: Any,
    requested_url: str,
    saved_path: Path,
    policy: SourcePolicy,
    max_bytes: int,
    require_archive: bool = False,
) -> dict[str, Any]:
    if not isinstance(response, dict) or response.get("ok") is not True:
        raise UpstreamError(f"公式ソースを確認できません: {requested_url}")
    if response.get("status") != 200:
        raise UpstreamError(
            f"公式ソースが成功応答を返しませんでした: {requested_url}: "
            f"HTTP {response.get('status')!r}"
        )

    final_url = response.get("url")
    saved = response.get("saved")
    byte_count = response.get("bytes")
    if not isinstance(final_url, str):
        raise UpstreamError("axの最終取得先URLがありません")
    ensure_allowed_url(final_url, policy, require_archive)
    if not isinstance(saved, str) or Path(saved).resolve() != saved_path.resolve():
        raise UpstreamError("axの保存先が指定した一時ファイルと一致しません")
    if type(byte_count) is not int or not 0 <= byte_count <= max_bytes:
        raise UpstreamError(f"axの取得サイズが不正です: {byte_count!r}")
    if not saved_path.is_file() or saved_path.stat().st_size != byte_count:
        raise UpstreamError("取得サイズと一時ファイルが一致しません")
    return {"url": final_url, "bytes": byte_count}


class AxBackend:
    name = "ax"

    def __init__(self, policy: SourcePolicy, executable: str) -> None:
        self.policy = policy
        self.executable = executable

    def _download_to_temporary_file(
        self,
        url: str,
        temporary_path: Path,
        max_bytes: int,
        require_archive: bool = False,
    ) -> dict[str, Any]:
        ensure_allowed_url(url, self.policy, require_archive)
        raw = run_ax_json(
            self.executable,
            [
                url,
                "-o",
                str(temporary_path),
                "-f",
                "--max-bytes",
                str(max_bytes),
                "-m",
                str(NETWORK_TIMEOUT_SECONDS),
            ],
        )
        return validate_ax_download(
            raw,
            url,
            temporary_path,
            self.policy,
            max_bytes,
            require_archive,
        )

    def find_current_archive(self, contract: dict[str, Any]) -> str:
        resource = contract["sources"]["resources_page"]
        resource_url = resource["url"]
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".dads-resources-", suffix=".html"
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        try:
            # parse modeだけではリダイレクト後のURLを検証できない。
            # fetch reportを先に検証し、同じaxで保存済みHTMLだけを解析する。
            receipt = self._download_to_temporary_file(
                resource_url, temporary_path, MAX_PAGE_BYTES
            )
            link_rule = resource["archive_link"]
            selector = (
                f"a[href*={json.dumps(link_rule['href_contains'])}]"
                f"[href$={json.dumps(link_rule['href_suffix'])}]"
            )
            rows = run_ax_json(
                self.executable,
                [
                    str(temporary_path),
                    selector,
                    "--row",
                    "href=@href",
                    "--json",
                    "--all",
                    "--no-cache",
                ],
            )
            if not isinstance(rows, list):
                raise UpstreamError(f"Markdown ZIPのリンクを解析できません: {rows!r}")
            hrefs: list[str] = []
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get("href"), str):
                    raise UpstreamError(
                        f"Markdown ZIPのリンクを解析できません: {row!r}"
                    )
                hrefs.append(row["href"])
            return require_unique_archive_url(
                resolve_archive_urls(
                    hrefs,
                    link_rule,
                    receipt["url"],
                    self.policy,
                )
            )
        finally:
            temporary_path.unlink(missing_ok=True)

    def download_archive(self, url: str, destination: Path) -> dict[str, Any]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", dir=destination.parent
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        try:
            receipt = self._download_to_temporary_file(
                url,
                temporary_path,
                MAX_ARCHIVE_BYTES,
                require_archive=True,
            )
            if not zipfile.is_zipfile(temporary_path):
                raise UpstreamError("取得したファイルは有効なZIPではありません")
            os.replace(temporary_path, destination)
            return receipt
        finally:
            temporary_path.unlink(missing_ok=True)


class StdlibBackend:
    name = "stdlib"

    def __init__(self, policy: SourcePolicy) -> None:
        self.policy = policy
        self.tls_context = ssl.create_default_context()
        self.tls_context.minimum_version = ssl.TLSVersion.TLSv1_2

    @contextlib.contextmanager
    def open_response(
        self,
        url: str,
        require_archive: bool = False,
        allowed_content_types: frozenset[str] | None = None,
    ) -> Iterator[Any]:
        ensure_allowed_url(url, self.policy, require_archive)
        request = Request(
            url,
            headers={
                "Accept": "*/*",
                "Accept-Encoding": "identity",
                "User-Agent": HTTP_USER_AGENT,
            },
        )
        opener = build_opener(
            # 環境プロキシを暗黙利用すると、端末ごとに取得経路が変わる。
            ProxyHandler({}),
            HTTPSHandler(context=self.tls_context),
            AllowedRedirectHandler(self.policy, require_archive),
        )
        try:
            response = opener.open(request, timeout=NETWORK_TIMEOUT_SECONDS)
        except (HTTPError, URLError, TimeoutError) as error:
            raise UpstreamError(
                f"公式ソースの取得に失敗しました: {url}: {error}"
            ) from error

        try:
            final_url = response.geturl()
            ensure_allowed_url(final_url, self.policy, require_archive)
            status = getattr(response, "status", None)
            if status != 200:
                raise UpstreamError(
                    f"公式ソースが成功応答を返しませんでした: "
                    f"{final_url}: HTTP {status!r}"
                )
            content_encoding = response.headers.get("Content-Encoding")
            if content_encoding and content_encoding.casefold() != "identity":
                raise UpstreamError(
                    f"圧縮されたHTTP応答は受け付けません: {content_encoding}"
                )
            content_type = response.headers.get_content_type().casefold()
            if allowed_content_types and content_type not in allowed_content_types:
                raise UpstreamError(
                    f"Content-Typeが更新契約と一致しません: {content_type}"
                )
            yield response
        finally:
            response.close()

    def find_current_archive(self, contract: dict[str, Any]) -> str:
        resource = contract["sources"]["resources_page"]
        with self.open_response(
            resource["url"], allowed_content_types=PAGE_CONTENT_TYPES
        ) as response:
            document_bytes = read_bounded_response(response, MAX_PAGE_BYTES)
            charset = response.headers.get_content_charset() or "utf-8"
            try:
                document = document_bytes.decode(charset)
            except (LookupError, UnicodeDecodeError) as error:
                raise UpstreamError(
                    f"公式リソースページをデコードできません: {charset}"
                ) from error
            final_url = response.geturl()
        parser = AnchorHrefParser()
        parser.feed(document)
        return require_unique_archive_url(
            resolve_archive_urls(
                parser.hrefs,
                resource["archive_link"],
                final_url,
                self.policy,
            )
        )

    def download_archive(self, url: str, destination: Path) -> dict[str, Any]:
        ensure_allowed_url(url, self.policy, require_archive=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", dir=destination.parent
        )
        temporary_path = Path(temporary_name)
        try:
            with self.open_response(url, require_archive=True) as response:
                declared_length = response_content_length(response)
                if declared_length is not None and declared_length > MAX_ARCHIVE_BYTES:
                    raise UpstreamError(
                        "ZIPの取得サイズが上限を超えています: "
                        f"{declared_length} > {MAX_ARCHIVE_BYTES}"
                    )
                with os.fdopen(descriptor, "wb") as output:
                    descriptor = -1
                    total = 0
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_ARCHIVE_BYTES:
                            raise UpstreamError(
                                "ZIPの取得サイズが上限を超えています: "
                                f"{MAX_ARCHIVE_BYTES}"
                            )
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                final_url = response.geturl()
            if not zipfile.is_zipfile(temporary_path):
                raise UpstreamError("取得したファイルは有効なZIPではありません")
            os.replace(temporary_path, destination)
            return {"url": final_url, "bytes": total}
        finally:
            if descriptor != -1:
                os.close(descriptor)
            temporary_path.unlink(missing_ok=True)


def response_content_length(response: Any) -> int | None:
    value = response.headers.get("Content-Length")
    if value is None:
        return None
    try:
        length = int(value)
    except (TypeError, ValueError) as error:
        raise UpstreamError(f"Content-Lengthを解析できません: {value!r}") from error
    if length < 0:
        raise UpstreamError(f"Content-Lengthが負の値です: {length}")
    return length


def read_bounded_response(response: Any, max_bytes: int) -> bytes:
    declared_length = response_content_length(response)
    if declared_length is not None and declared_length > max_bytes:
        raise UpstreamError(
            f"取得サイズが上限を超えています: {declared_length} > {max_bytes}"
        )

    chunks: list[bytes] = []
    total = 0
    while chunk := response.read(min(1024 * 1024, max_bytes + 1 - total)):
        total += len(chunk)
        if total > max_bytes:
            raise UpstreamError(f"取得サイズが上限を超えています: {max_bytes}")
        chunks.append(chunk)
    return b"".join(chunks)


def select_fetch_backend(
    requested: str,
    contract: dict[str, Any],
) -> FetchBackend:
    policy = build_source_policy(contract)
    if requested == "stdlib":
        return StdlibBackend(policy)
    executable = shutil.which("ax")
    selected = "ax" if requested == "auto" and executable else requested
    if selected == "auto":
        return StdlibBackend(policy)
    if selected == "ax":
        if executable is None:
            raise UpstreamError(
                "axコマンドが見つかりません。"
                "--fetch-backend stdlibを使うか、axをインストールしてください"
            )
        return AxBackend(policy, executable)
    raise UpstreamError(f"未対応の取得バックエンドです: {requested}")
