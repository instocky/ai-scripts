"""Тесты SqliteSpanExporter.

Используем MagicMock(spec=ReadableSpan) чтобы не зависеть от конкретной
версии OTel SDK и не поднимать полный TracerProvider в unit-тестах.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.trace import Status, StatusCode
from opentelemetry.trace.span import SpanContext, TraceFlags

from tracing.exporter import SqliteSpanExporter
from tracing.store import TraceStore


def _make_span(
    *,
    trace_id: int,
    span_id: int,
    name: str,
    parent_id: int | None,
    duration_ms: float = 100.0,
    attributes: dict[str, Any] | None = None,
    status: StatusCode = StatusCode.OK,
    service_name: str = "test_svc",
) -> MagicMock:
    span = MagicMock(spec=ReadableSpan)
    span.get_span_context.return_value = SpanContext(
        trace_id=trace_id,
        span_id=span_id,
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    if parent_id is not None:
        parent = MagicMock()
        parent.span_id = parent_id
        span.parent = parent
    else:
        span.parent = None
    span.name = name
    span.kind.name = "INTERNAL"
    span.start_time = 1_000_000_000
    span.end_time = 1_000_000_000 + int(duration_ms * 1_000_000)
    span.status = Status(status)
    span.attributes = attributes or {}
    span.events = []
    span.resource = Resource.create({"service.name": service_name})
    scope = MagicMock()
    scope.name = "test"
    scope.version = "0.1.0"
    span.instrumentation_scope = scope
    return span


def test_export_groups_by_trace(tmp_path: Path) -> None:
    store = TraceStore(tmp_path / "t.db")
    exporter = SqliteSpanExporter(store)

    trace_id = 0x1234
    spans = [
        _make_span(trace_id=trace_id, span_id=1, name="root", parent_id=None, duration_ms=200),
        _make_span(trace_id=trace_id, span_id=2, name="child", parent_id=1, duration_ms=50),
    ]
    result = exporter.export(spans)
    assert result == SpanExportResult.SUCCESS

    rec = store.get_trace("00000000000000000000000000001234")
    assert rec is not None
    assert rec["service"] == "test_svc"
    assert rec["duration_ms"] == pytest.approx(200.0)
    assert rec["status"] == "OK"
    assert len(rec["raw_spans"]["spans"]) == 2


def test_export_aggregates_cost_from_attributes(tmp_path: Path) -> None:
    store = TraceStore(tmp_path / "t.db")
    exporter = SqliteSpanExporter(store)

    trace_id = 0xAAAA
    spans = [
        _make_span(
            trace_id=trace_id, span_id=1, name="root", parent_id=None,
            duration_ms=100, attributes={"gen_ai.usage.cost": 0.005},
        ),
        _make_span(
            trace_id=trace_id, span_id=2, name="chat", parent_id=1,
            duration_ms=80,
            attributes={
                "gen_ai.usage.cost": 0.012,
                "gen_ai.response.model": "openai/gpt-4o-mini",
                "gen_ai.usage.input_tokens": 100,
                "gen_ai.usage.output_tokens": 50,
            },
        ),
    ]
    exporter.export(spans)
    rec = store.get_trace("0000000000000000000000000000aaaa")
    assert rec["total_cost_usd"] == pytest.approx(0.017)


def test_export_propagates_error_status(tmp_path: Path) -> None:
    store = TraceStore(tmp_path / "t.db")
    exporter = SqliteSpanExporter(store)

    spans = [
        _make_span(
            trace_id=0xBBB, span_id=1, name="root", parent_id=None,
            status=StatusCode.ERROR,
        ),
    ]
    exporter.export(spans)
    rec = store.get_trace("00000000000000000000000000000bbb")
    assert rec["status"] == "ERROR"