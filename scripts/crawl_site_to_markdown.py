import argparse
import asyncio
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crawler import CrawlConfig, SiteMarkdownCrawlerService  # noqa: E402


DEFAULT_DELAY = "2-5"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Crawl a site and save pages as markdown with manifest.json.",
    )
    parser.add_argument("--url", required=True, help="Base URL to crawl")
    parser.add_argument(
        "--max-pages",
        type=int,
        required=True,
        help="Maximum number of pages to crawl",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory where crawl output will be written",
    )
    parser.add_argument(
        "--delay",
        default=DEFAULT_DELAY,
        help=(
            "Random delay between requests in seconds. "
            "Use N-M for a range or N for a fixed delay. Default: 2-5"
        ),
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    config = CrawlConfig(
        base_url=args.url,
        max_pages=args.max_pages,
        output_dir=args.output_dir,
        delay_range_seconds=parse_delay_range(args.delay),
    )
    service = SiteMarkdownCrawlerService()
    result = await service.crawl(config)

    has_failures = result.manifest.stats.failed > 0
    print("Crawl finished with errors" if has_failures else "Crawl completed")
    print(f"Base URL: {result.manifest.base_url}")
    print(f"Storage path: {result.storage_path}")
    print(f"Delay range (s): {format_delay_range(config.delay_range_seconds)}")
    print(f"Discovered: {result.manifest.stats.discovered}")
    print(f"Crawled: {result.manifest.stats.crawled}")
    print(f"Saved: {result.manifest.stats.saved}")
    print(f"Failed: {result.manifest.stats.failed}")
    print(f"Skipped: {result.manifest.stats.skipped}")
    print(f"Duration (ms): {result.duration_ms}")

    if has_failures:
        first_error = next(
            (page.get("error") for page in result.manifest.pages if page.get("error")),
            None,
        )
        if first_error:
            print(f"First error: {first_error}", file=sys.stderr)
        return 1

    return 0


def parse_delay_range(raw_value: str) -> tuple[float, float]:
    value = raw_value.strip()
    if not value:
        msg = "delay value must not be empty"
        raise ValueError(msg)

    if "-" in value:
        left, right = value.split("-", maxsplit=1)
        min_delay = float(left)
        max_delay = float(right)
    else:
        min_delay = float(value)
        max_delay = min_delay

    if min_delay < 0 or max_delay < 0:
        msg = "delay values must be non-negative"
        raise ValueError(msg)
    if min_delay > max_delay:
        msg = "delay min value must be less than or equal to max"
        raise ValueError(msg)

    return min_delay, max_delay


def format_delay_range(delay_range: tuple[float, float]) -> str:
    min_delay, max_delay = delay_range
    if min_delay == max_delay:
        return f"{min_delay:g}"
    return f"{min_delay:g}-{max_delay:g}"


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(_run(args))
    except Exception as exc:
        print(f"[crawler] failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())