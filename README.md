# 0630_ai-scripts

Сборник AI-tools — небольших скриптов, демонстрирующих разные аспекты работы с LLM: структурный вывод, парсинг неструктурированного текста, планирование изменений.

Базовый стек — **Instructor + Ollama + Pydantic v2**. Ollama отдаёт OpenAI-совместимый API, Instructor строит JSON Schema из Pydantic-модели, валидирует ответ и возвращает готовый типизированный объект.

---

## Стек

- Python 3.11+
- Ollama (локальный inference)
- Instructor
- OpenAI SDK (Ollama OpenAI-compatible endpoint)
- Pydantic v2

---

## Быстрый старт

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

Скопировать `.env.example` в `.env` и заполнить при необходимости:

```text
OLLAMA_BASE_URL=http://192.168.0.99:11434/v1
OLLAMA_MODEL=ornith:latest
OLLAMA_API_KEY=ollama
```

Запуск любого скрипта:

```powershell
python scripts\<script_name>.py
```

---

## Tools

Скрипты добавляются по мере проработки тем. Каждый идёт с детальным описанием в `docs/`.

| #   | Скрипт                      | Пакет                                                                                                       | Что демонстрирует                                                                                            | Документация                                   |
| --- | --------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | ---------------------------------------------- |
| 1   | `scripts/get_user.py`       | [Instructor](https://pypi.org/project/instructor/)                                                          | Базовый сценарий: Instructor извлекает `User(name, age, city)` из одного предложения                         | [docs/get_user.md](docs/get_user.md)           |
| 2   | `scripts/parse_issue.py`    | [Instructor](https://pypi.org/project/instructor/)                                                          | Enum + вложенная модель + список + валидация + retries на малой модели                                       | [docs/parse_issue.md](docs/parse_issue.md)     |
| 3   | `scripts/simple_pipeline.py` | [OpenLIT](https://github.com/openlit/openlit) + OTel → SQLite                                              | Минимальный pipeline (HTTP + compute + lookup) для smoke-теста трейсера. Без LLM, без API-ключей             | —                                              |
| 4   | `scripts/openlit_pipeline.py` | [OpenLIT](https://github.com/openlit/openlit) + OTel → SQLite (+ OTLP escape hatch)                      | Сквозной pipeline через OpenTelemetry: HTTP → Pydantic → lookup → LLM ×2. Трейсы — в SQLite                  | [docs/openlit_pipeline.md](docs/openlit_pipeline.md) |
| 5   | `scripts/view_traces.py`    | CLI viewer для `src/tracing/`                                                                              | `python scripts\view_traces.py --last 24h --limit 20` — таблица trace'ов; `--by-span` — дерево span'ов        | —                                              |

---

## Tracing

Сквозная аналитика для любого скрипта через единый сервис `src/tracing/`.

**В скрипте (3 строки):**

```python
from tracing import init_tracing, get_tracer, finish_tracing

init_tracing(service_name=__name__, db_path="traces.db")
tracer = get_tracer(__name__)
# ... ручные span'ы и/или auto-instrumentation OpenLIT ...
finish_tracing()  # в конце __main__
```

**Просмотр (CLI):**

```powershell
python scripts\view_traces.py --last 24h --limit 20
python scripts\view_traces.py --by-span --service openlit_pipeline --last 24h
python scripts\view_traces.py --service simple_pipeline --last 1h --by-span
python scripts\view_traces.py --trace f90823cc...   # конкретный trace
```

**Что в SQLite (`<root>/traces.db`):**

- `traces` — по одной строке на каждый pipeline run: `service`, `started_at`, `duration_ms`, `total_cost_usd`, `status` (OK/ERROR), плюс `raw_spans_json` со всеми span'ами для ad-hoc.
- `idx_traces_service_started` — для быстрой фильтрации по сервису и времени.

**Переменные окружения:**

- `TRACING_DB_PATH` — путь к SQLite (default: `<root>/traces.db`).
- `OTEL_EXPORTER_OTLP_ENDPOINT` — если задан, OpenLIT параллельно шлёт OTLP в этот endpoint (Phoenix / SigNoz) в дополнение к SQLite.
- `OTEL_TRACES_EXPORTER` / `OTEL_METRICS_EXPORTER` / `OTEL_LOGS_EXPORTER` — по умолчанию `init_tracing()` ставит `none` (отключает OpenLIT Console*-фоллбэк). Для своего Phoenix-сценария выставите `otlp`.
- `OPENLIT_PRICING_JSON` — путь к кастомному pricing (для date-suffix OpenRouter-моделей).

---

## Planned

См. [BACKLOG.md](BACKLOG.md) — что планируется добавить следующим.

---

## Дополнительно

- [CHANGELOG.md](CHANGELOG.md) — что менялось в проекте.
- `notes.md` — личный scratchpad автора (не часть документации проекта).
