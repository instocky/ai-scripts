"""Тесты TraceStore."""
from __future__ import annotations

from pathlib import Path

import pytest

from tracing.store import TraceStore


@pytest.fixture
def store(tmp_path: Path) -> TraceStore:
    return TraceStore(tmp_path / "test.db")


def test_upsert_and_get(store: TraceStore) -> None:
    record = {
        "trace_id": "abc123",
        "service": "test_svc",
        "started_at": 1000.0,
        "ended_at": 1001.5,
        "duration_ms": 1500.0,
        "status": "OK",
        "total_cost_usd": 0.00123,
    }
    raw = {"spans": [{"name": "root", "duration_ms": 1500}]}
    store.upsert_trace(record, raw)

    got = store.get_trace("abc123")
    assert got is not None
    assert got["trace_id"] == "abc123"
    assert got["service"] == "test_svc"
    assert got["total_cost_usd"] == pytest.approx(0.00123)
    assert got["raw_spans"]["spans"][0]["name"] == "root"


def test_upsert_updates_existing(store: TraceStore) -> None:
    rec = {
        "trace_id": "x", "service": "s", "started_at": 1.0, "ended_at": 2.0,
        "duration_ms": 1000.0, "status": "OK", "total_cost_usd": 0.0,
    }
    store.upsert_trace(rec, {"spans": []})
    rec["status"] = "ERROR"
    rec["total_cost_usd"] = 0.05
    store.upsert_trace(rec, {"spans": []})

    got = store.get_trace("x")
    assert got["status"] == "ERROR"
    assert got["total_cost_usd"] == pytest.approx(0.05)


def test_list_filters_by_service_and_since(store: TraceStore) -> None:
    base = {
        "service": "svc_a", "started_at": 100.0, "ended_at": 101.0,
        "duration_ms": 1000.0, "status": "OK", "total_cost_usd": 0.0,
    }
    store.upsert_trace({**base, "trace_id": "a1"}, {"spans": []})
    store.upsert_trace(
        {**base, "trace_id": "a2", "service": "svc_b", "started_at": 200.0},
        {"spans": []},
    )
    store.upsert_trace(
        {**base, "trace_id": "a3", "started_at": 300.0},
        {"spans": []},
    )

    rows = store.list_traces(service="svc_a")
    assert {r["trace_id"] for r in rows} == {"a1", "a3"}

    rows = store.list_traces(since=150.0)
    assert {r["trace_id"] for r in rows} == {"a2", "a3"}

    rows = store.list_traces(limit=1)
    assert len(rows) == 1
    # newest first
    assert rows[0]["trace_id"] == "a3"


def test_schema_idempotent(tmp_path: Path) -> None:
    """Повторная инициализация по тому же пути не падает."""
    TraceStore(tmp_path / "x.db")
    TraceStore(tmp_path / "x.db")