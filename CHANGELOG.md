# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-07-01

### Added

- `src/tracing/` — сервис сквозной аналитики: `init_tracing()` подключает OpenLIT + OpenTelemetry SDK, регистрирует `SqliteSpanExporter` (единственный span-exporter), печатает компактный stdout-итог через `finish_tracing()`. Схема SQLite: `traces` с денормализованными колонками для фильтрации (`service / started_at / duration_ms / total_cost_usd / status`) + один блоб `raw_spans_json` со всеми span'ами trace'а для ad-hoc/SQL-извлечений.
- `src/tracing/cli.py` — viewer: `--service`, `--last 30m/2h/7d`, `--limit`, `--by-span` (span-дерево последнего trace'а под фильтрами), `--trace <id>`. Запуск через `scripts/view_traces.py` (см. ниже).
- `scripts/simple_pipeline.py` — минимальный pipeline (HTTP + compute + lookup, без LLM, без API-ключей) для smoke-теста трейсера и второй pipeline с интеграцией — `scripts/openlit_pipeline.py`.
- `scripts/view_traces.py` — wrapper для CLI viewer'а: добавляет `src/` в `sys.path` (по аналогии с `*_pipeline.py`); избавляет от необходимости выставлять `PYTHONPATH=src` для `python -m tracing`.
- `tests/test_tracing/test_store.py`, `test_exporter.py`, `test_smoke.py` — unit + smoke (subprocess-запуск `simple_pipeline.py` + проверка `traces.db`).
- Pricing-patch перенесён из `openlit_pipeline.py` в `src/tracing/pricing.py::install_openlit_pricing()`.

### Changed

- `scripts/openlit_pipeline.py` — блок init (50+ строк ручного OpenLIT setup, pricing patch, OTEL provider, ConsoleSpanProcessor) свёрнут в 4 строки: `init_tracing(service_name=..., db_path=...)` + `tracer = get_tracer(...)`. В `__main__` добавлен `finish_tracing()` для гарантированного flush BSP. JSON-дамп `RESULT` убран из `__main__` (результат остаётся в БД, в `raw_spans_json` events Pydantic-модели).
- `README.md` — добавлена секция «Tracing» с примерами; tools-table обновлён: убран `logfire_pipeline.py`, добавлены `simple_pipeline.py` и `view_traces.py`.

### Fixed

- **Stdout-summary не совпадал с `traces.db`** — ранее `SqliteSpanExporter.export()` печатал `[tracing] one-liner` сразу при получении первой порции span'ов от BatchSpanProcessor. Для долгих LLM-pipeline'ов первая порция приходила до того, как chat-span с `gen_ai.usage.cost` закрывался, и stdout показывал `cost=$0.00000 status=UNSET` тогда как в БД (через UPSERT) уже лежали `$0.00066 status=OK`. Exporter помечал trace_id в `_printed` и больше не печатал. **Решение:** stdout-summary перенесён из exporter'а (BSP-thread) в `finish_tracing()` (main thread, после `force_flush()`) — теперь читает финальные данные из БД и stdout гарантированно совпадает с ней.
- **OpenLIT ConsoleExporter спам в stdout** — без `OTEL_EXPORTER_OTLP_ENDPOINT` `openlit.init()` сам ставит `ConsoleSpanExporter` (см. `openlit/otel/tracing.py:120-131`) и `ConsoleMetricReader`, которые выгружают в stdout полный JSON всех span'ов и метрик. **Решение:** в `init_tracing()` перед `openlit.init()` выставляются `OTEL_TRACES_EXPORTER=none`, `OTEL_METRICS_EXPORTER=none`, `OTEL_LOGS_EXPORTER=none` (стандартный механизм OTel SDK, OpenLIT его уважает). `setdefault` — пользовательский `otlp` для Phoenix-сценария не перетирается.

### Removed

- `scripts/logfire_pipeline.py` — отказались от Logfire как от эксперимента (cloud-first, нет локального persistent-режима, для OpenRouter cost нужно городить ручной `annotate_cost`).
- `logfire` из `requirements.txt`.

## [0.3.0] - 2026-06-30

### Added

- `scripts/openlit_pipeline.py` — сквозной pipeline с трассировкой через OpenLIT + OpenTelemetry. Тот же сценарий (HTTP → Pydantic → lookup → LLM ×2), но без workaround'ов из Logfire-версии: нет `MODEL_PRICING`, нет `annotate_cost`, нет `llm_call()` helper'а, нет ручных Chat Completion span'ов.
- `pricing.json` — кастомный файл с ценами на используемые OpenRouter-модели (`z-ai/glm-5.2`, `openai/gpt-4o-mini`). Подключается через `openlit.init(pricing_json=...)` или env `OPENLIT_PRICING_JSON`. Формат: USD за 1K токенов.
- `docs/openlit_pipeline.md` — детальная документация нового скрипта, архитектурного паттерна «OTel = контракт, backend = pluggable» и формата `pricing.json`.
- `openlit` — добавлен в `requirements.txt`. `arize-phoenix` намеренно НЕ добавлен (Phoenix — это backend, поднимается отдельно).

### Changed

- `AGENTS.md` — раздел «Observability» полностью переписан под OpenTelemetry: вместо Logfire-специфичных инструкций — общий принцип «OTel = контракт, backend = pluggable», список поддерживаемых backend'ов (stdout / Phoenix / SigNoz), правила auto-instrumentation и manual spans для бизнес-логики, инструкция по `pricing.json`.
- `README.md` — добавлена строка #4 в tools-table (`scripts/openlit_pipeline.py`); строка #3 (`logfire_pipeline.py`) помечена как legacy reference для сравнения подходов.

### Fixed

- **Cost-калькуляция для OpenRouter date-suffix моделей.** Эмпирически подтверждено: встроенная price-таблица OpenLIT не покрывает маршруты с date-suffix (например `z-ai/glm-5.2-20260616`), и `gen_ai.usage.cost` для таких моделей приходит как `0` — та же проблема, что была у Logfire + `genai_prices`. Решено через `pricing_json` (вместо ручного `MODEL_PRICING`/`annotate_cost` как в Logfire-версии) — OpenLIT берёт цены из нашего JSON, без workaround-кода в pipeline'е.
- **Корректировка документации:** убрано утверждение «OpenLIT знает цены из коробки» (для date-suffix OpenRouter не работает), исправлено утверждение «urllib не auto-instruments» (OpenLIT тянет `opentelemetry-instrumentation-urllib` как зависимость).

### Notes

- `scripts/logfire_pipeline.py` и `docs/logfire_pipeline.md` оставлены без изменений — служат legacy reference для сравнения двух подходов (Logfire auto-instrument workaround vs OpenLIT out-of-the-box).
- Дефолтный backend для MVP — `stdout` (ConsoleSpanExporter). Phoenix подключается опционально через `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:6006` после `phoenix serve`. SigNoz и Live Monitoring перенесены в BACKLOG.
- **Известные ограничения** (полный список — в `docs/openlit_pipeline.md` → «Известные ограничения»): (1) cost = 0 для моделей вне `pricing.json`; (2) ручной `fetch_external_user` span дублирует auto-instrumented urllib (сосуществуют нормально); (3) ConsoleSpanExporter дублирует вывод в Phoenix-режиме (шум, легко отключается).

## [0.2.0] - 2026-06-30

### Honest reassessment: Logfire не подошёл для MVP-сценария

Изначальная цель: лёгкий drop-in трассировщик для MVP. Реальность по итогу работы:

- Logfire 4.x — **cloud-first**: локального persistent-режима нет (`logfire web` отсутствует, SQLite не пишется, без токена только stdout).
- Для UI в Cloud нужен полный bootstrap: `logfire auth` → `logfire projects new` → `logfire projects use` (каждый шаг со своими квирками CLI).
- Для OpenRouter-моделей cost в UI не подтягивается — нужна ручная аннотация через OTel API (custom pricing dict + ручные span'ы, т.к. `logfire.instrument_openai()` закрывает свой span до нашего annotate_cost).
- Итого: тот же operational overhead, от которого уходили от Langfuse (ClickHouse-стек), просто в другой обёртке.

**Решение:** скрипт остаётся как есть (работающий cloud-демо + stdout fallback), но **не рекомендуется как primary-решение для MVP**. Для MVP-проектов лучше:

- structured `logging` в JSON (stdlib, без зависимостей);
- `phoenix serve` от Arize (open source, SQLite-режим, локальный UI);
- полноценный OTLP → SigNoz (если хочется web UI локально и есть Docker).

### Fixed

- `scripts/logfire_pipeline.py` и `docs/logfire_pipeline.md` — приведены к реальности Logfire 4.x:
  - удалена команда `logfire web` (в v4.x её нет, был неверный совет);
  - `logfire.configure(send_to_logfire=False)` заменено на `send_to_logfire="if-token-present"` — без токена трейсы идут в stdout (Rich-формат), с токеном — в Logfire Cloud;
  - в доке раздел "Просмотр трейсов" переписан с тремя реальными режимами (stdout / Cloud / OTLP-бэкенд);
  - в скрипте финальный print "NEXT" обновлён под новые инструкции;
  - поправлена команда авторизации: `logfire auth --region us|eu` (НЕ `logfire auth login` — такой подкоманды нет, реальная команда `logfire auth` без подкоманды, CLI --help неполный);
  - добавлена аннотация стоимости: `MODEL_PRICING` dict + `annotate_cost()` helper + вызовы после каждого LLM-вызова. Без неё OpenRouter-модели показывают "Unknown" в UI (Logfire берёт pricing из `genai_prices`, OpenRouter-маршруты с date-suffix там отсутствуют);
  - `classify_intent` переведён с Instructor на сырой OpenAI + `Intent.model_validate_json()` — для прямого доступа к `usage`. Теряем Instructor-retry на этой операции, но получаем корректную cost-аннотацию;
  - `logfire.instrument_openai()` убран, Chat Completion span создаётся вручную через `llm_call()` хелпер. Причина: auto-instrument закрывает свой span ДО того, как наш `annotate_cost()` успевает проставить `genai.usage.cost` — атрибут уходил в родительский span, UI показывал Unknown. Ручной span = cost на месте.

### Added

- `scripts/logfire_pipeline.py` — сквозной pipeline (HTTP → Pydantic → lookup → LLM ×2) под трассировкой Logfire. Демонстрирует auto-instrumentation OpenAI SDK и Pydantic, ручные `logfire.span()` для HTTP/lookup, корневой span для связки всего trace'а.
- `docs/logfire_pipeline.md` — детальная документация скрипта.
- `logfire` — добавлен в `requirements.txt`.
- `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` — добавлены в `.env.example` (`.env` не трогаем, только шаблон).
- `.logfire/` — добавлен в `.gitignore` (локальный SQLite Logfire).
- `AGENTS.md` — новый раздел "Observability": правила использования Logfire (local-only, auto-instrumentation, запрет на логирование секретов).

## [0.1.1] - 2026-06-30

### Added

- `scripts/parse_issue.py` — разбор bug-report в типизированный `Issue` (Enum `Priority`, вложенная модель `FileChange`, список файлов, `summary`, `estimated_hours`).
- `docs/parse_issue.md` — детальная документация скрипта.
- `README.md` — точка входа в проект: стек, быстрый старт, список tools.
- `BACKLOG.md` — что планируется добавить.

### Changed (parse_issue iteration)

- `scripts/parse_issue.py` — итерация по качеству вывода на малой модели:
  - добавлен `SYSTEM_PROMPT` с правилами маппинга файлов на причины и переписывания summary;
  - добавлен `Field(description=...)` на `reason` и `summary` (модель понимает, что туда писать);
  - добавлен `min_length=3` на `reason` (пустые строки падают на валидации);
  - добавлен `max_retries=3` в Instructor (структурные ошибки триггерят retry, реально сработал на первом прогоне — модель выдала dict вместо array).

## [0.1.0] - 2026-06-30

### Added

- `scripts/get_user.py` — первый пример: Instructor + Ollama извлекают `User(name, age, city)` из одного предложения.
- `requirements.txt` — `instructor`, `openai>=1.50.0`, `pydantic>=2.7`, `python-dotenv`.
- `.env.example` — шаблон для `OLLAMA_BASE_URL` / `OLLAMA_MODEL` / `OLLAMA_API_KEY`.
- `notes.md` — личный scratchpad автора.
