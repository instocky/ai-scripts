from __future__ import annotations

import asyncio
from pathlib import Path

from crawler.client import ClientPageResult
from crawler.models import CrawlConfig, CrawledPage
from crawler.services import SiteMarkdownCrawlerService


class FakeCrawlerClient:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def crawl_page(
        self,
        url: str,
        *,
        discovered_from: str | None,
    ) -> ClientPageResult:
        self.events.append(f"crawl:{url}")
        page = CrawledPage(
            url=url,
            normalized_url=url,
            discovered_from=discovered_from,
            title="Test page",
            markdown="# Test",
            status="success",
            error=None,
            crawled_at="2026-07-02T00:00:00Z",
        )
        links = ["https://example.com/next/"] if url == "https://example.com/" else []
        return ClientPageResult(
            page=page,
            links=links,
            crawler_version="test",
        )


def test_first_request_has_no_startup_delay(
    monkeypatch,
    tmp_path: Path,
) -> None:
    client = FakeCrawlerClient()
    service = SiteMarkdownCrawlerService(client=client)
    sleep_calls: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)
        client.events.append(f"sleep:{delay}")

    monkeypatch.setattr("crawler.services.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("crawler.services._random_delay_seconds", lambda _: 3.5)

    result = asyncio.run(
        service.crawl(
            CrawlConfig(
                base_url="https://example.com",
                max_pages=2,
                output_dir=tmp_path,
            )
        )
    )

    assert client.events == [
        "crawl:https://example.com/",
        "sleep:3.5",
        "crawl:https://example.com/next/",
    ]
    assert sleep_calls == [3.5]
    assert result.manifest.stats.crawled == 2
    assert result.manifest.stats.saved == 2
