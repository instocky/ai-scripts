from __future__ import annotations

import asyncio
import random
from collections import deque
from dataclasses import replace
from datetime import UTC, datetime
from time import perf_counter

from crawler.client import Crawl4AiClient
from crawler.models import CrawlConfig, CrawlRunResult, RunManifest, RunStats
from crawler.storage import MarkdownStorage
from crawler.url_utils import is_same_domain, normalize_url


class SiteMarkdownCrawlerService:
    def __init__(self, client: Crawl4AiClient | None = None) -> None:
        self._client = client or Crawl4AiClient()

    async def crawl(self, config: CrawlConfig) -> CrawlRunResult:
        started_at = _utc_now()
        start_time = perf_counter()
        normalized_base_url = normalize_url(config.base_url, config.base_url)
        if normalized_base_url is None:
            msg = f"Invalid base_url: {config.base_url}"
            raise ValueError(msg)

        storage = MarkdownStorage(config.output_dir)
        storage_path = storage.prepare_run(normalized_base_url, started_at)

        queue: deque[tuple[str, str | None]] = deque([(normalized_base_url, None)])
        queued: set[str] = {normalized_base_url}
        visited: set[str] = set()
        manifest_pages: list[dict[str, object]] = []
        stats = RunStats(discovered=1)
        crawler_version: str | None = None
        is_first_request = True

        while queue and stats.crawled < config.max_pages:
            current_url, discovered_from = queue.popleft()
            if current_url in visited:
                stats.skipped += 1
                continue

            if not is_first_request:
                await asyncio.sleep(_random_delay_seconds(config))

            visited.add(current_url)
            page_result = await self._client.crawl_page(
                current_url,
                discovered_from=discovered_from,
            )
            is_first_request = False
            crawler_version = crawler_version or page_result.crawler_version
            stats.crawled += 1

            markdown_path: str | None = None
            if page_result.page.status == "success":
                stats.saved += 1
                markdown_path = storage.save_page(page_result.page)
            else:
                stats.failed += 1

            manifest_pages.append(
                {
                    "url": page_result.page.url,
                    "normalized_url": page_result.page.normalized_url,
                    "title": page_result.page.title,
                    "status": page_result.page.status,
                    "markdown_path": markdown_path,
                    "error": page_result.page.error,
                    "discovered_from": page_result.page.discovered_from,
                }
            )

            for link in page_result.links:
                normalized_link = normalize_url(page_result.page.url, link)
                if normalized_link is None:
                    stats.skipped += 1
                    continue
                if config.same_domain_only and not is_same_domain(
                    normalized_base_url,
                    normalized_link,
                ):
                    stats.skipped += 1
                    continue
                if normalized_link in visited or normalized_link in queued:
                    stats.skipped += 1
                    continue

                queue.append((normalized_link, page_result.page.normalized_url))
                queued.add(normalized_link)
                stats.discovered += 1

        finished_at = _utc_now()
        duration_ms = int((perf_counter() - start_time) * 1000)
        manifest = RunManifest(
            version=1,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            base_url=normalized_base_url,
            crawler="crawl4ai",
            crawler_version=crawler_version,
            storage_dir=storage_path.as_posix(),
            stats=replace(stats),
            pages=manifest_pages,
        )
        storage.write_manifest(manifest)
        return CrawlRunResult(
            manifest=manifest,
            storage_path=storage_path,
            duration_ms=duration_ms,
        )


def _random_delay_seconds(config: CrawlConfig) -> float:
    min_delay, max_delay = config.delay_range_seconds
    return random.uniform(min_delay, max_delay)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")