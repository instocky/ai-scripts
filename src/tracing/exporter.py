"""OTel SpanExporter → SQLite.

Получает батч ReadableSpan'ов от BatchSpanProcessor, группирует по trace_id,
считает summary (service / duration / status / cost) и кладёт в TraceStore.

Stdout-summary намеренно НЕ печатается отсюда: BSP экспортит span'ы
порциями, первая порция может прийти до того, как chat-span'ы с cost
закроются. Если бы exporter печатал summary на первой порции —
stdout и БД разошлись бы (БД через UPSERT накапливает финальные данные).
Stdout-summary печатается из `finish_tracing()` после force_flush — там
гарантированно полный trace.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from .store import TraceStore

# OpenTelemetry semantic conventions для LLM-метрик (см. GenAI semconv)
_ATTR_COST = "gen_ai.usage.cost"
_ATTR_MODEL = "gen_ai.response.model"
_ATTR_INPUT_TOKENS = "gen_ai.usage.input_tokens"
_ATTR_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
_ATTR_SERVICE_NAME = "service.name"

_STATUS_PRIORITY = {"ERROR": 3, "OK": 2, "UNSET": 1}


def _format_hex(value: int, width: int) -> str:
    return format(value, f"0{width}x")


def _span_to_dict(span: ReadableSpan) -> dict[str, Any]:
    """Сериализация ReadableSpan → JSON-safe dict."""
    ctx = span.get_span_context()
    parent = span.parent
    return {
        "trace_id": _format_hex(ctx.trace_id, 32),
        "span_id": _format_hex(ctx.span_id, 16),
        "parent_span_id": _format_hex(parent.span_id, 16) if parent else None,
        "name": span.name,
        "kind": span.kind.name,
        "start_time_ns": span.start_time,
        "end_time_ns": span.end_time,
        "duration_ms": (span.end_time - span.start_time) / 1_000_000,
        "status": span.status.status_code.name,
        "attributes": dict(span.attributes),
        "events": [
            {
                "name": e.name,
                "timestamp_ns": e.timestamp,
                "attributes": dict(e.attributes),
            }
            for e in span.events
        ],
        "resource_attributes": dict(span.resource.attributes),
        "instrumentation_scope": {
            "name": span.instrumentation_scope.name,
            "version": span.instrumentation_scope.version,
        },
    }


def _summarize(spans: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Агрегировать summary по trace'у из его span'ов."""
    started_at_ns = min(s["start_time_ns"] for s in spans)
    ended_at_ns = max(s["end_time_ns"] for s in spans)

    # service.name — из resource любого span'а (в рамках trace'а ресурс общий)
    service = ""
    for s in spans:
        service = s["resource_attributes"].get(_ATTR_SERVICE_NAME, "")
        if service:
            break

    total_cost = 0.0
    for s in spans:
        cost = s["attributes"].get(_ATTR_COST)
        if isinstance(cost, (int, float)):
            total_cost += float(cost)

    # Худший статус в trace'е: ERROR > OK > UNSET
    worst = max(
        (s["status"] for s in spans),
        key=lambda x: _STATUS_PRIORITY.get(x, 0),
        default="UNSET",
    )

    return {
        "service": service or "unknown",
        "started_at": started_at_ns / 1_000_000_000,
        "ended_at": ended_at_ns / 1_000_000_000,
        "duration_ms": (ended_at_ns - started_at_ns) / 1_000_000,
        "status": worst,
        "total_cost_usd": total_cost,
    }


class SqliteSpanExporter(SpanExporter):
    """OpenTelemetry SpanExporter → SQLite."""

    def __init__(self, store: TraceStore):
        self._store = store

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            by_trace: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for span in spans:
                tid = _format_hex(span.get_span_context().trace_id, 32)
                by_trace[tid].append(_span_to_dict(span))

            for trace_id, trace_spans in by_trace.items():
                summary = _summarize(trace_spans)
                record = {"trace_id": trace_id, **summary}
                self._store.upsert_trace(record, {"spans": trace_spans})
            return SpanExportResult.SUCCESS
        except Exception:  # noqa: BLE001
            return SpanExportResult.FAILED

    def shutdown(self) -> None:
        # Никаких внешних ресурсов, SQLite закрывается per-call.
        return None

    def force_flush(self, timeout_millis: int = 30_000) -> bool:  # noqa: ARG002
        # SQLite insert синхронный — после export() всё уже в файле.
        return True