from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from crawler.models import CrawledPage
from crawler.url_utils import normalize_url


@dataclass(slots=True)
class ClientPageResult:
    page: CrawledPage
    links: list[str]
    crawler_version: str | None


class Crawl4AiClient:
    crawler_name = "crawl4ai"

    async def crawl_page(
        self,
        url: str,
        *,
        discovered_from: str | None,
    ) -> ClientPageResult:
        crawled_at = _utc_now()
        try:
            crawler_module = import_module("crawl4ai")
            crawler_class = getattr(crawler_module, "AsyncWebCrawler")
        except ModuleNotFoundError as exc:
            msg = (
                "crawl4ai is not installed. Install it in the project venv before "
                "running the crawler CLI."
            )
            raise RuntimeError(msg) from exc

        browser_error = _get_missing_browser_error()
        if browser_error is not None:
            page = CrawledPage(
                url=url,
                normalized_url=normalize_url(url, url) or url,
                discovered_from=discovered_from,
                title=None,
                markdown="",
                status="error",
                error=browser_error,
                crawled_at=crawled_at,
            )
            return ClientPageResult(
                page=page,
                links=[],
                crawler_version=_get_crawler_version(),
            )

        crawler_version = _get_crawler_version()

        try:
            base_directory = _get_crawler_base_directory()
            async with crawler_class(base_directory=str(base_directory)) as crawler:
                result = await crawler.arun(url=url)
        except Exception as exc:
            page = CrawledPage(
                url=url,
                normalized_url=normalize_url(url, url) or url,
                discovered_from=discovered_from,
                title=None,
                markdown="",
                status="error",
                error=f"{type(exc).__name__}: {exc}",
                crawled_at=crawled_at,
            )
            return ClientPageResult(page=page, links=[], crawler_version=crawler_version)

        final_url = _pick_first_value(result, "url", "final_url", "response_url") or url
        normalized_url = normalize_url(final_url, final_url) or final_url
        markdown = _extract_markdown(result)
        title = _pick_first_value(result, "title", "page_title")
        links = _extract_links(result, final_url)

        page = CrawledPage(
            url=final_url,
            normalized_url=normalized_url,
            discovered_from=discovered_from,
            title=title,
            markdown=markdown,
            status="success",
            error=None,
            crawled_at=crawled_at,
        )
        return ClientPageResult(page=page, links=links, crawler_version=crawler_version)


def _extract_markdown(result: Any) -> str:
    markdown = getattr(result, "markdown", None)
    if isinstance(markdown, str):
        return markdown

    if markdown is not None:
        raw_markdown = getattr(markdown, "raw_markdown", None)
        if isinstance(raw_markdown, str):
            return raw_markdown

        fit_markdown = getattr(markdown, "fit_markdown", None)
        if isinstance(fit_markdown, str):
            return fit_markdown

        nested_raw = getattr(fit_markdown, "raw_markdown", None)
        if isinstance(nested_raw, str):
            return nested_raw

    return ""


def _extract_links(result: Any, base_url: str) -> list[str]:
    raw_links = getattr(result, "links", None)
    if not raw_links:
        return []

    links: list[str] = []
    seen: set[str] = set()

    def add(candidate: str | None) -> None:
        if not candidate:
            return
        normalized = normalize_url(base_url, candidate)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        links.append(normalized)

    if isinstance(raw_links, dict):
        for section in raw_links.values():
            if isinstance(section, list):
                for item in section:
                    if isinstance(item, str):
                        add(item)
                    elif isinstance(item, dict):
                        add(item.get("href") or item.get("url"))
    elif isinstance(raw_links, list):
        for item in raw_links:
            if isinstance(item, str):
                add(item)
            elif isinstance(item, dict):
                add(item.get("href") or item.get("url"))

    return links


def _get_missing_browser_error() -> str | None:
    browser_root = _get_playwright_browsers_root()
    if browser_root is None:
        return None

    if _has_playwright_chromium(browser_root):
        return None

    return (
        "Playwright browser executable is missing. Install Chromium in the active "
        "venv with: python -m playwright install chromium"
    )


def _get_crawler_base_directory() -> Path:
    base_directory = Path.cwd() / ".crawl4ai"
    base_directory.mkdir(parents=True, exist_ok=True)
    return base_directory


def _get_playwright_browsers_root() -> Path | None:
    configured_path = os.getenv("PLAYWRIGHT_BROWSERS_PATH")
    if configured_path and configured_path != "0":
        return Path(configured_path).expanduser()

    home = Path.home()
    if sys.platform == "win32":
        return home / "AppData" / "Local" / "ms-playwright"
    if sys.platform == "darwin":
        return home / "Library" / "Caches" / "ms-playwright"
    return home / ".cache" / "ms-playwright"


def _has_playwright_chromium(browser_root: Path) -> bool:
    if not browser_root.exists():
        return False

    candidates = [
        browser_root.glob("chromium-*/*/chrome.exe"),
        browser_root.glob("chromium-*/*/chrome"),
    ]
    return any(path.is_file() for pattern in candidates for path in pattern)


def _pick_first_value(result: Any, *field_names: str) -> str | None:
    for field_name in field_names:
        value = getattr(result, field_name, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _get_crawler_version() -> str | None:
    try:
        return version("crawl4ai")
    except PackageNotFoundError:
        return None


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")