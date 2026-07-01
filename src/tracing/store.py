"""SQLite store для трейсов.

Схема денормализована под требования просмотра:
  - колонки по которым фильтруют (service, started_at, duration, cost, status)
  - один блоб `raw_spans_json` со всеми span'ами trace'а для ad-hoc/SQL-извлечений

Не делаем retention, не нормализуем span'ы в отдельные таблицы — для MVP
несколько тысяч trace'ов в SQLite летают.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
  trace_id         TEXT PRIMARY KEY,
  service          TEXT NOT NULL,
  started_at       REAL NOT NULL,
  ended_at         REAL,
  duration_ms      REAL,
  status           TEXT,
  total_cost_usd   REAL DEFAULT 0,
  raw_spans_json   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_traces_service_started
  ON traces(service, started_at DESC);
"""


class TraceStore:
    """Тонкая обёртка над SQLite: upsert / list / get_one."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def upsert_trace(
        self,
        record: dict[str, Any],
        raw_spans: dict[str, Any],
    ) -> None:
        """Сохранить/обновить trace (UPSERT по trace_id).

        Повторный вызов с тем же trace_id перезаписывает — это позволяет
        BatchSpanProcessor'у поставлять span'ы порциями: итоговый UPSERT
        после force_flush содержит полный набор.
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO traces (
                    trace_id, service, started_at, ended_at, duration_ms,
                    status, total_cost_usd, raw_spans_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trace_id) DO UPDATE SET
                    service        = excluded.service,
                    started_at     = excluded.started_at,
                    ended_at       = excluded.ended_at,
                    duration_ms    = excluded.duration_ms,
                    status         = excluded.status,
                    total_cost_usd = excluded.total_cost_usd,
                    raw_spans_json = excluded.raw_spans_json
                """,
                (
                    record["trace_id"],
                    record["service"],
                    record["started_at"],
                    record["ended_at"],
                    record["duration_ms"],
                    record["status"],
                    record["total_cost_usd"],
                    json.dumps(raw_spans, ensure_ascii=False),
                ),
            )

    def get_trace(self, trace_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM traces WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()
        return _row_to_dict(row) if row else None

    def list_traces(
        self,
        *,
        service: str | None = None,
        since: float | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM traces WHERE 1=1"
        params: list[Any] = []
        if service:
            sql += " AND service = ?"
            params.append(service)
        if since is not None:
            sql += " AND started_at >= ?"
            params.append(since)
        sql += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    # raw_spans_json парсим обратно для удобства CLI/тестов
    try:
        d["raw_spans"] = json.loads(d.pop("raw_spans_json"))
    except (KeyError, TypeError, json.JSONDecodeError):
        pass
    return d