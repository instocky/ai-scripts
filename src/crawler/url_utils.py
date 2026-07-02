from __future__ import annotations

from pathlib import Path, PurePosixPath
from urllib.parse import urljoin, urlparse, urlunparse


def normalize_url(base_url: str, candidate_url: str) -> str | None:
    if not candidate_url:
        return None

    resolved_url = urljoin(base_url, candidate_url.strip())
    parsed = urlparse(resolved_url)

    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    if not parsed.netloc:
        return None

    host = parsed.hostname.lower() if parsed.hostname else ""
    if not host:
        return None

    port = parsed.port
    if port and not _is_default_port(parsed.scheme.lower(), port):
        netloc = f"{host}:{port}"
    else:
        netloc = host

    normalized_path = _normalize_path(parsed.path)
    return urlunparse((parsed.scheme.lower(), netloc, normalized_path, "", "", ""))


def is_same_domain(base_url: str, candidate_url: str) -> bool:
    base_host = urlparse(base_url).hostname
    candidate_host = urlparse(candidate_url).hostname
    if not base_host or not candidate_host:
        return False
    return base_host.lower() == candidate_host.lower()


def url_to_pages_path(url: str) -> Path:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if not path:
        return Path("index.md")

    pure_path = PurePosixPath(path.lstrip("/"))
    if path.endswith(".html"):
        target = pure_path.with_suffix(".md")
    elif pure_path.suffix:
        target = pure_path.with_suffix(f"{pure_path.suffix}.md")
    else:
        target = pure_path.parent / f"{pure_path.name}.md"

    return Path(*target.parts)


def _normalize_path(path: str) -> str:
    raw_path = path or "/"
    pure_path = PurePosixPath(raw_path)
    normalized = pure_path.as_posix()

    if normalized.endswith("/index.html"):
        normalized = normalized[: -len("index.html")]
    elif normalized == "/index.html":
        normalized = "/"

    if normalized != "/" and normalized.endswith("/"):
        normalized = normalized.rstrip("/")

    last_segment = normalized.rsplit("/", maxsplit=1)[-1]
    if normalized != "/" and "." not in last_segment:
        normalized = f"{normalized}/"

    if not normalized.startswith("/"):
        normalized = f"/{normalized}"

    return normalized


def _is_default_port(scheme: str, port: int) -> bool:
    return (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
