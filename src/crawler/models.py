from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CrawlConfig:
    base_url: str
    max_pages: int
    output_dir: Path
    same_domain_only: bool = True
    delay_range_seconds: tuple[float, float] = (2.0, 5.0)

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir)
        if self.max_pages < 1:
            msg = "max_pages must be greater than 0"
            raise ValueError(msg)

        min_delay, max_delay = self.delay_range_seconds
        if min_delay < 0 or max_delay < 0:
            msg = "delay_range_seconds values must be non-negative"
            raise ValueError(msg)
        if min_delay > max_delay:
            msg = "delay_range_seconds min value must be less than or equal to max"
            raise ValueError(msg)


@dataclass(slots=True)
class CrawledPage:
    url: str
    normalized_url: str
    discovered_from: str | None
    title: str | None
    markdown: str
    status: str
    error: str | None
    crawled_at: str


@dataclass(slots=True)
class RunStats:
    discovered: int = 0
    crawled: int = 0
    saved: int = 0
    failed: int = 0
    skipped: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(slots=True)
class RunManifest:
    version: int
    started_at: str
    finished_at: str
    duration_ms: int
    base_url: str
    crawler: str
    crawler_version: str | None
    storage_dir: str
    stats: RunStats
    pages: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "base_url": self.base_url,
            "crawler": self.crawler,
            "crawler_version": self.crawler_version,
            "storage_dir": self.storage_dir,
            "stats": self.stats.to_dict(),
            "pages": self.pages,
        }


@dataclass(slots=True)
class CrawlRunResult:
    manifest: RunManifest
    storage_path: Path
    duration_ms: int