# scripts/simple_pipeline.py
#
# Минимальный pipeline для smoke-теста трейсера: ручные span'ы, без LLM,
# без внешних API-ключей. Запускается где угодно и оставляет запись в traces.db.
#
# Запуск:
#     python scripts\simple_pipeline.py
#
# Просмотр:
#     python -m tracing --service simple_pipeline --last 24h
#     python -m tracing --by-span --last 24h

import sys
import urllib.request
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from opentelemetry.trace import Status, StatusCode  # noqa: E402

from tracing import default_db_path, finish_tracing, get_tracer, init_tracing  # noqa: E402


init_tracing(
    service_name=Path(__file__).stem,
    db_path=default_db_path(),
)
tracer = get_tracer(__name__)


def step_http(url: str) -> int:
    """GET-запрос наружу; возвращает HTTP status."""
    with tracer.start_as_current_span("step_http", attributes={"url": url}):
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                return resp.status
        except Exception:
            return 0


def step_compute(n: int) -> int:
    """Имитация CPU-работы с ручным span и event'ом."""
    with tracer.start_as_current_span("step_compute", attributes={"iterations": n}) as span:
        total = 0
        for i in range(n):
            total += i
        span.add_event("loop_done", attributes={"sum": total})
        return total


def step_lookup(key: str) -> dict:
    """In-memory lookup — тот же паттерн, что в openlit_pipeline."""
    store = {
        "alpha": {"tier": "pro", "region": "eu"},
        "beta": {"tier": "free", "region": "us"},
    }
    with tracer.start_as_current_span("step_lookup", attributes={"key": key}):
        return store.get(key, {"tier": "free", "region": "unknown"})


def run() -> dict:
    with tracer.start_as_current_span("simple_pipeline") as root:
        status = step_http("https://example.com")
        total = step_compute(1000)
        record = step_lookup("alpha")
        # Без явного OK OTel SDK оставит StatusCode.UNSET на root — это
        # "статус неизвестен", не "успех". В трейсе хотим видеть чёткое
        # OK/ERROR, поэтому ставим явно. При исключении выше — UNSET
        # останется как есть (что норм: видно, что run не дошёл до OK).
        root.set_status(Status(StatusCode.OK))
    return {"http_status": status, "compute_sum": total, "record": record}


if __name__ == "__main__":
    try:
        result = run()
        print("RESULT:", result)
    finally:
        finish_tracing()