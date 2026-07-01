"""CLI viewer для traces.db.

Запуск:
    python -m tracing.cli --db traces.db --service openlit_pipeline --last 7d --limit 20
    python -m tracing.cli --db traces.db --trace <trace_id>
    python -m tracing.cli --db traces.db --by-span --last 24h
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from .store import TraceStore

_TIME_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _parse_since(spec: str) -> float:
    """`7d` → unix timestamp 7 дней назад (UTC)."""
    unit = spec[-1]
    if unit not in _TIME_UNITS or not spec[:-1].isdigit():
        raise SystemExit(
            f"[tracing] bad --last format: {spec!r} (use e.g. 30m / 2h / 7d)"
        )
    n = int(spec[:-1])
    delta_seconds = n * _TIME_UNITS[unit]
    return (datetime.now(timezone.utc) - timedelta(seconds=delta_seconds)).timestamp()


def _fmt_time(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _fmt_status(status: str) -> str:
    return {"ERROR": "ERR", "OK": "OK"}.get(status, "—")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tracing",
        description="Просмотр трассировок из SQLite.",
    )
    p.add_argument("--db", default="traces.db", help="путь к traces.db")
    p.add_argument("--service", help="фильтр по service.name")
    p.add_argument("--last", help="фильтр по времени: 30m / 2h / 7d")
    p.add_argument("--limit", type=int, default=20, help="максимум строк (default 20)")
    p.add_argument(
        "--trace",
        help="показать span-дерево конкретного trace_id (полный 32-hex)",
    )
    p.add_argument(
        "--by-span",
        action="store_true",
        help="span-дерево последнего trace'а под текущими фильтрами",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    store = TraceStore(args.db)

    if args.trace or args.by_span:
        return _show_span_tree(store, args)
    return _show_table(store, args)


def _show_table(store: TraceStore, args: argparse.Namespace) -> int:
    since = _parse_since(args.last) if args.last else None
    rows = store.list_traces(service=args.service, since=since, limit=args.limit)
    if not rows:
        print("[tracing] no traces for current filters")
        return 0

    headers = ("started_at", "service", "status", "duration", "cost", "trace")
    widths = (19, 28, 6, 10, 12, 10)

    def _line(cells: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(width) for cell, width in zip(cells, widths, strict=False))

    print(_line(headers))
    print(_line(tuple("-" * w for w in widths)))
    for r in rows:
        print(
            _line(
                (
                    _fmt_time(r["started_at"]),
                    r["service"],
                    _fmt_status(r["status"]),
                    f"{r['duration_ms'] / 1000:.2f}s",
                    f"${r['total_cost_usd']:.5f}",
                    r["trace_id"][:8],
                )
            )
        )
    return 0


def _show_span_tree(store: TraceStore, args: argparse.Namespace) -> int:
    trace_id = args.trace
    if not trace_id:
        since = _parse_since(args.last) if args.last else None
        rows = store.list_traces(
            service=args.service, since=since, limit=1
        )
        if not rows:
            print("[tracing] no traces for current filters")
            return 1
        trace_id = rows[0]["trace_id"]

    record = store.get_trace(trace_id)
    if record is None:
        print(f"[tracing] trace not found: {trace_id}")
        return 1

    spans = record.get("raw_spans", {}).get("spans", [])
    if not spans:
        print("[tracing] no spans in trace")
        return 0

    # Группируем по parent_span_id
    children: dict[str | None, list[dict]] = {}
    for s in spans:
        parent = s["parent_span_id"]
        children.setdefault(parent, []).append(s)
    for v in children.values():
        v.sort(key=lambda x: x["start_time_ns"])

    roots = children.get(None, [])
    if not roots:
        print("[tracing] no root span (orphans)")
        return 0

    print(
        f"[tracing] {record['service']} · "
        f"{record['status']} · "
        f"{record['duration_ms'] / 1000:.2f}s · "
        f"${record['total_cost_usd']:.5f} · "
        f"trace={record['trace_id']}"
    )
    print()

    def render(span: dict, depth: int) -> None:
        prefix = "  " * depth + ("├── " if depth > 0 else "")
        cost = span["attributes"].get("gen_ai.usage.cost")
        cost_str = f"  ${float(cost):.5f}" if isinstance(cost, (int, float)) else ""
        print(f"{prefix}{span['name']}  ({span['duration_ms']:.1f}ms){cost_str}")
        for child in children.get(span["span_id"], []):
            render(child, depth + 1)

    for root in roots:
        render(root, 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())