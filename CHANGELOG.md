# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
