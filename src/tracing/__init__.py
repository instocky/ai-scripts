"""Tracing service: OpenLIT + OpenTelemetry → SQLite.

Единая точка входа для любого скрипта:

    from tracing import init_tracing, get_tracer, finish_tracing

    init_tracing(service_name=__name__, db_path="traces.db")
    tracer = get_tracer(__name__)

    with tracer.start_as_current_span("step", attributes={...}):
        ...

    finish_tracing()  # в конце __main__

После init() скрипт может использовать как auto-instrumentation OpenLIT
(OpenAI / Pydantic / etc.), так и ручные span'ы через tracer.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from .exporter import SqliteSpanExporter
from .pricing import install_openlit_pricing
from .store import TraceStore

_initialized = False
_store: TraceStore | None = None  # для finish_tracing()
_process_start_ts: float | None = None  # для finish_tracing stdout-summary


def _project_root() -> Path:
    """Корень проекта: на 2 уровня выше src/tracing/.

    `src/tracing/__init__.py` → `<root>/src/tracing/` → `<root>`.
    """
    return Path(__file__).resolve().parent.parent.parent


def default_db_path() -> Path:
    """Env `TRACING_DB_PATH` или `<root>/traces.db`."""
    env = os.getenv("TRACING_DB_PATH")
    return Path(env) if env else _project_root() / "traces.db"


def init_tracing(service_name: str, db_path: Path | str | None = None) -> TraceStore:
    """Инициализация трассировки.

    Идемпотентна — повторный вызов возвращает уже созданный store.

    Делает:
      1. Поднимает OpenLIT pricing patch (см. pricing.py).
      2. `openlit.init(...)` — ставит OTel SDK TracerProvider и
         auto-instrumentation OpenAI / Pydantic / etc.
      3. Регистрирует SqliteSpanExporter через BatchSpanProcessor.
         Это ЕДИНСТВЕННЫЙ exporter — никакого Console-дублирования.

    Args:
        service_name: имя сервиса для resource attribute `service.name`.
            Пробивается через env `OTEL_SERVICE_NAME` (стандарт OTel SDK).
        db_path: путь к SQLite. None → env `TRACING_DB_PATH` или
            `<root>/traces.db`.

    Returns:
        Инициализированный TraceStore (на случай прямого доступа).
    """
    global _initialized, _store, _process_start_ts
    if db_path is None:
        db_path = default_db_path()

    store = TraceStore(db_path)
    _store = store

    if _process_start_ts is None:
        # Запоминаем момент init'а — finish_tracing читает из БД только
        # trace'ы, начатые не раньше этого timestamp'а.
        _process_start_ts = time.time()

    if not _initialized:
        # OTEL_SERVICE_NAME — стандартная переменная OTel SDK; OpenLIT
        # пробрасывает её в resource при создании TracerProvider.
        os.environ["OTEL_SERVICE_NAME"] = service_name

        # Отключаем дефолтные Console*Exporter'ы OpenLIT — без этого при
        # отсутствии OTEL_EXPORTER_OTLP_ENDPOINT openlit сам ставит
        # ConsoleSpanExporter (см. openlit/otel/tracing.py:120-131) и
        # ConsoleMetricReader, и спамит полным JSON в stdout.
        # Значение "none" для OTEL_TRACES_EXPORTER etc. — стандартный
        # механизм OTel SDK, OpenLIT его уважает.
        for var in ("OTEL_TRACES_EXPORTER", "OTEL_METRICS_EXPORTER", "OTEL_LOGS_EXPORTER"):
            os.environ.setdefault(var, "none")

        install_openlit_pricing()

        import openlit
        openlit.init(
            otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
            pricing_json=None,
        )

        from opentelemetry import trace
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        provider = trace.get_tracer_provider()
        real = getattr(provider, "_real_provider", provider) or provider
        if hasattr(real, "add_span_processor"):
            real.add_span_processor(BatchSpanProcessor(SqliteSpanExporter(store)))

        _initialized = True

    return store


def get_tracer(name: str):
    """Получить OTel tracer (по имени модуля/скрипта)."""
    from opentelemetry import trace
    return trace.get_tracer(name)


def finish_tracing() -> None:
    """Сбросить все буферизованные span'ы в SQLite + напечатать компактный
    stdout-summary по всем trace'ам, начатым после `init_tracing()`.

    Вызывать в конце `__main__` (в finally), иначе:
      - часть span'ов BatchSpanProcessor не успеет экспортнуть до
        завершения процесса;
      - stdout-summary не напечатается.

    Summary печатается из main thread, после `force_flush()` —
    гарантированно полные данные из БД (а не частичные из первой порции BSP).
    """
    from opentelemetry import trace
    provider = trace.get_tracer_provider()
    real = getattr(provider, "_real_provider", provider) or provider
    if hasattr(real, "force_flush"):
        real.force_flush()

    if _store is not None and _process_start_ts is not None:
        try:
            rows = _store.list_traces(since=_process_start_ts, limit=50)
            for r in rows:
                _print_summary_line(r)
        except Exception:  # noqa: BLE001
            # stdout-summary — best effort, не роняем скрипт на косяках БД.
            pass


def _print_summary_line(record: dict) -> None:
    duration_s = record["duration_ms"] / 1000
    cost = record["total_cost_usd"]
    print(
        f"[tracing] {record['service']} · "
        f"{record['status']} · "
        f"{duration_s:.2f}s · "
        f"${cost:.5f} · "
        f"trace={record['trace_id'][:8]}",
        flush=True,
    )


__all__ = [
    "init_tracing",
    "get_tracer",
    "finish_tracing",
    "default_db_path",
    "TraceStore",
    "SqliteSpanExporter",
]