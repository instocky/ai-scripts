from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from crawler.models import CrawledPage, RunManifest
from crawler.url_utils import url_to_pages_path


class MarkdownStorage:
    def __init__(self, output_dir: Path) -> None:
        self._output_dir = Path(output_dir)
        self._run_dir: Path | None = None
        self._pages_dir: Path | None = None

    def prepare_run(self, base_url: str, started_at: str) -> Path:
        domain = _domain_from_url(base_url)
        timestamp = _timestamp_from_iso(started_at)
        run_dir = self._output_dir / domain / timestamp
        pages_dir = run_dir / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        self._run_dir = run_dir
        self._pages_dir = pages_dir
        return run_dir

    def save_page(self, page: CrawledPage) -> str:
        if self._run_dir is None or self._pages_dir is None:
            msg = "prepare_run() must be called before save_page()"
            raise RuntimeError(msg)

        relative_path = url_to_pages_path(page.normalized_url)
        target_path = self._pages_dir / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(_render_markdown(page), encoding="utf-8")
        return (Path("pages") / relative_path).as_posix()

    def write_manifest(self, manifest: RunManifest) -> Path:
        if self._run_dir is None:
            msg = "prepare_run() must be called before write_manifest()"
            raise RuntimeError(msg)

        manifest_path = self._run_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return manifest_path


def _render_markdown(page: CrawledPage) -> str:
    front_matter = [
        "---",
        f"url: {page.url}",
        f"title: {_yaml_scalar(page.title)}",
        f"status: {page.status}",
        f"crawled_at: {page.crawled_at}",
        "---",
        "",
    ]
    body = page.markdown.rstrip()
    return "\n".join(front_matter) + (body + "\n" if body else "")


def _yaml_scalar(value: str | None) -> str:
    if value is None:
        return "null"
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _domain_from_url(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return parsed.hostname or "unknown-domain"


def _timestamp_from_iso(value: str) -> str:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.astimezone(UTC).strftime("%Y%m%d_%H%M%S")
