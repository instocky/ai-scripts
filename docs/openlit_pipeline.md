# docs/openlit_pipeline.md

План миграции с Logfire Cloud на **OpenLIT + OpenTelemetry** для сквозного pipeline-трейсинга. Документ для старта в новой сессии.

---

## TL;DR

**Что строим:** `scripts/openlit_pipeline.py` — тот же сценарий, что в `logfire_pipeline.py` (HTTP → Pydantic → lookup → LLM ×2), но через OpenLIT. Без ручных span'ов, без кастомного `MODEL_PRICING`, без облачного auth-bootstrap'а.

**Цель:** переписать демо так, чтобы backend можно было менять одной env-переменной (stdout → Phoenix → SigNoz), а код не трогать.

**Версия:** `0.3.0`.

---

## Контекст: почему именно OpenLIT

История решений (полная — в `CHANGELOG.md` → `[0.2.0]`):

1. **Старт**: искали лёгкий local-tracer для MVP, отказались от Langfuse (ClickHouse-стек тяжёлый).
2. **Попробовали Logfire 4.x**: оказалось, что в v4.x нет локального persistent-режима и `logfire web`. Cloud-first SaaS. Чтобы завести UI — нужны auth + project create + project use + active project, плюс custom-pricing-аннотации через OTel API (Logfire не знает OpenRouter-модели в `genai_prices`). Итог: тот же overhead, от которого уходили.
3. **Переосмысление**: для MVP «просто и локально» правильный стек — **OpenTelemetry как контракт + взаимозаменяемый backend**. OpenLIT — лучший кандидат на роль LLM-instrumentation поверх OTel.

---

## Архитектурный паттерн

```
Ваш код
   │
   ▼
OpenLIT  ←── auto-instruments LiteLLM / OpenAI / Anthropic / Ollama / agents
   │
   ▼
OpenTelemetry SDK (OTel GenAI semantic conventions)
   │
   ▼
OTLP
   │
   ├──▶ stdout / JSON-файл       (dev, 0 инфры)
   ├──▶ phoenix serve            (локальный UI, SQLite/Postgres)
   ├──▶ SigNoz / Jaeger / Tempo  (full APM, Docker)
   └──▶ Honeycomb / Grafana Cloud (enterprise SaaS)
```

**Ключевое условие**: инструментация строго следует [OTel GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/), тогда backend можно менять без правок кода.

---

## Что переносим из текущей сессии

Из `scripts/logfire_pipeline.py` берём **структуру pipeline**, не код:

| Шаг                                 | Что демонстрирует  | Аналог в OpenLIT                                                                                                                               |
| ----------------------------------- | ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `fetch_external_user`               | HTTP-запрос наружу | `urllib` (auto-instrumented через `opentelemetry-instrumentation-urllib` — тянется как зависимость OpenLIT) + ручной span для бизнес-контекста |
| `validate_user`                     | Pydantic-валидация | Без изменений — auto-Pydantic-span от OpenLIT                                                                                                  |
| `lookup_internal_data`              | in-memory store    | Ручной `otel.trace` span                                                                                                                       |
| `classify_intent`                   | LLM-вызов #1       | **OpenLIT auto-instrumentation** + Instructor tool call                                                                                        |
| `generate_answer`                   | LLM-вызов #2       | То же                                                                                                                                          |
| Корневой span `handle_user_request` | Связка всех шагов  | Без изменений                                                                                                                                  |

---

## Плюшки (insights из текущей сессии — зафиксировать в новой)

### 1. OpenTelemetry = контракт, backend = pluggable

```python
# Единственная точка выбора backend'а — env-переменная
import os
from opentelemetry import trace
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
# или: from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

if os.getenv("OTEL_EXPORTER") == "phoenix":
    from phoenix.otel import register
    tracer_provider = register(project_name="0630_ai-scripts")
elif os.getenv("OTEL_EXPORTER") == "signoz":
    # OTLP → SigNoz
    exporter = OTLPSpanExporter(endpoint="http://localhost:4317")
    tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
else:  # stdout / file
    tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
```

### 2. OpenLIT даёт почти всё «из коробки» — кроме cost для date-suffix моделей

```python
import openlit

openlit.init(
    otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),  # опционально
    pricing_json=os.getenv("OPENLIT_PRICING_JSON") or "pricing.json",  # опционально
    # auto-instruments: OpenAI, Anthropic, Cohere, Mistral, Ollama, vLLM,
    # Bedrock, VertexAI, LangChain, LlamaIndex, Haystack
    # captures: model, provider, tokens, cost (по встроенным price-таблицам),
    # latency, tool calls, retrieval, system_instructions
)
```

**Caveat про cost:** OpenLIT поставляет встроенный `pricing.json` с ценами
на популярные модели (OpenAI, Anthropic, Mistral, часть OpenRouter), но
**для моделей с date-suffix** (например `z-ai/glm-5.2-20260616`) lookup
возвращает 0 — `gen_ai.usage.cost` будет пустым. Это та же проблема,
что была у Logfire + `genai_prices`, но с элегантным решением: подсунуть
свой `pricing.json` через параметр `pricing_json` (или env
`OPENLIT_PRICING_JSON`). Без ручного кода в pipeline'е.

Формат custom pricing — структура как у [встроенного `pricing.json`](https://github.com/openlit/openlit/blob/main/assets/pricing.json):

```json
{
  "chat": {
    "z-ai/glm-5.2": {
      "promptPrice": 0.00094,
      "completionPrice": 0.003
    },
    "openai/gpt-4o-mini": {
      "promptPrice": 0.00015,
      "completionPrice": 0.0006
    }
  }
}
```

> ⚠️ Цены в `pricing.json` указаны **за 1K токенов**, а не за 1M. OpenRouter
> `z-ai/glm-5.2` стоит $0.94/M input → `promptPrice: 0.00094` (÷ 1000).

Источник цен: <https://openrouter.ai/models/<model>>.

### 3. Phoenix 4.x+ — реальный кандидат для локального dev

```bash
pip install arize-phoenix
phoenix serve
# UI: http://localhost:6006
```

SQLite-режим для dev. PostgreSQL-режим тянет 100k+ spans/день (для prod тоже годится).

### 4. SigNoz — full APM self-hosted

Если нужны traces + metrics + logs + alerts в одном — Docker Compose с SigNoz. Не 1:1 заменяет Datadog (нет managed integrations и alerting-экосистемы), но ядро закрывает.

### 5. Manual spans — только для бизнес-логики

`logfire.span("fetch_external_user")` нужен только если шаг не auto-instrumented. Для HTTP, SQL, LLM — auto-instrumentation покрывает. Меньше кода = меньше багов.

---

## План реализации (v0.3.0)

### Шаг 1 — минимальный pipeline

Создать `scripts/openlit_pipeline.py`:

```python
import openlit
from openai import OpenAI
from pydantic import BaseModel
import os
from pathlib import Path

# 1. Init OpenLIT — auto-instruments OpenAI + Pydantic.
#    instrument_pydantic() отдельно НЕ вызываем: OpenLIT делает это в init().
#
# 2. Custom pricing.json — для моделей с date-suffix (z-ai/glm-5.2-20260616),
#    которых нет во встроенной price-таблице OpenLIT. Формат: см. ниже секцию
#    «Custom pricing.json». Override через env OPENLIT_PRICING_JSON.
_pricing = os.getenv("OPENLIT_PRICING_JSON") or str(Path(__file__).parent.parent / "pricing.json")
if not Path(_pricing).exists():
    _pricing = None

openlit.init(
    otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
    pricing_json=_pricing,
)

# 3. Pipeline как раньше — HTTP, Pydantic, in-memory lookup, LLM ×2
# 4. Трейсы автоматически идут через OTel SDK
```

Без custom cost-логики в коде, без manual Chat Completion span'ов, без `llm_call()` helper'а.

**Instructor:** в `classify_intent` возвращаем Instructor (`instructor.from_openai(client)`),
который был снят в Logfire-версии ради доступа к `usage`. С OpenLIT usage доступен
через OTel-атрибуты на auto-instrumented chat-completion span — считать вручную
не нужно. Эмпирически проверено: race на закрытии span отсутствует, cost-атрибут
проставляется на chat-span, не на родительский (в отличие от Logfire).

### Custom pricing.json

Файл `pricing.json` в корне проекта (override через `OPENLIT_PRICING_JSON`).
Структура как у [встроенного `pricing.json` OpenLIT](https://github.com/openlit/openlit/blob/main/assets/pricing.json):

```json
{
  "chat": {
    "z-ai/glm-5.2": {
      "promptPrice": 0.00094,
      "completionPrice": 0.003
    },
    "z-ai/glm-5.2-20260616": {
      "promptPrice": 0.00094,
      "completionPrice": 0.003
    },
    "openai/gpt-4o-mini": {
      "promptPrice": 0.00015,
      "completionPrice": 0.0006
    }
  }
}
```

> ⚠️ Цены в `pricing.json` указаны **за 1K токенов** (не за 1M, как в Logfire-версии).
> OpenRouter `z-ai/glm-5.2` стоит $0.94/M input → `promptPrice: 0.00094` (÷ 1000).

Источник цен: <https://openrouter.ai/models/<model>>.

Без этого файла (или если модели в нём нет) `gen_ai.usage.cost` будет `0` —
это та же проблема, что у Logfire, и `pricing_json` — её каноническое решение
для OpenLIT (без workaround-кода в pipeline'е).

### Шаг 2 — переключение backend'а через env

**Default для MVP — stdout** (без `OTEL_EXPORTER_OTLP_ENDPOINT`).
Phoenix — опциональный «включи и посмотри UI» режим; в CI/acceptance
прогоне не требуется.

```powershell
# Default: stdout (без OTLP endpoint)
python scripts\openlit_pipeline.py

# Phoenix (локальный UI) — опционально, для визуальной проверки
phoenix serve
# в другом терминале:
$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:6006/v1/traces"
python scripts\openlit_pipeline.py
# → открыть http://localhost:6006

# SigNoz (Docker) — future work, см. BACKLOG
docker compose up -d signoz
$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:4317"
python scripts\openlit_pipeline.py
```

### Шаг 3 — docs

Обновить `AGENTS.md` раздел Observability под OpenTelemetry (см. ниже),
добавить строку в `README.md` tools-table, при завершении — запись
в `CHANGELOG.md` → `[0.3.0]` и перенос `## Next → ## Done` в `BACKLOG.md`.

> **Шаг 4 (Live Monitoring, A/B prompts, SigNoz) — пропущен для v0.3.0**,
> перенесён в BACKLOG как future work. Не блокирует релиз.

---

## Что НЕ делать (workaround'ы, которые прошли в Logfire-версии)

| Anti-pattern                                                         | Почему больше не нужно                                                                                          |
| -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `MODEL_PRICING = {...}` dict + ручной расчёт                         | OpenLIT знает цены популярных моделей из коробки; для остальных — `pricing_json` (см. Custom pricing.json ниже) |
| `annotate_cost()` + `set_attribute("genai.usage.cost", ...)`         | OpenLIT проставляет cost на chat-span автоматически (но **только если модель есть в price-таблице**)            |
| `llm_call()` helper с manual `logfire.span(...)` для Chat Completion | OpenLIT auto-instrumentation закрывает chat-span корректно — race на закрытии отсутствует                       |
| `classify_intent` на сыром OpenAI вместо Instructor                  | С OpenLIT можно вернуть Instructor — usage доступен через OTel атрибуты                                         |
| `logfire.auth` + `logfire projects new` + `logfire projects use`     | Не нужны — Phoenix/SigNoz стартуют локально без auth                                                            |
| Удалять `scripts/logfire_pipeline.py`                                | Оставлен как legacy reference для сравнения подходов в одном репозитории                                        |

---

## Команды для старта в новой сессии

```powershell
# 1. Установить OpenLIT (Phoenix — опционально, только если хотим UI)
pip install openlit
pip install arize-phoenix   # опционально

# 2. Скопировать структуру из scripts/logfire_pipeline.py
#    (HTTP → Pydantic → lookup → LLM ×2)

# 3. Заменить Logfire-init на OpenLIT-init
# 4. Заменить все logfire.span(...) на trace.get_tracer(__name__).start_as_current_span(...)
# 5. Убрать MODEL_PRICING, annotate_cost, llm_call, custom cost logic
# 6. Вернуть Instructor в classify_intent (был снят в Logfire-версии)

# 7. Тестовый прогон: stdout (default)
python scripts\openlit_pipeline.py

# 8. Опционально: с Phoenix для просмотра UI
phoenix serve
# в другом терминале:
$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:6006/v1/traces"
python scripts\openlit_pipeline.py
# → открыть http://localhost:6006
```

---

## Память (для контекста в новой сессии)

В `~/.mavis/agents/mavis/memory/MEMORY.md` уже зафиксировано:

- `Logfire ≠ лёгкая local-замена Langfuse` — почему мы ушли
- `LLM observability для LiteLLM-стека: OpenLIT + Phoenix` — правильный путь
- `OpenTelemetry = контракт, backend = pluggable` — главный архитектурный принцип

Эти три записи — основной контекст. Начни сессию с их чтения.

---

## Acceptance criteria для v0.3.0

- [ ] `scripts/openlit_pipeline.py` запускается и работает в stdout-режиме (default)
- [ ] Без `MODEL_PRICING`, `annotate_cost`, `llm_call`, custom-pricing кода в pipeline
- [ ] `grep -r "MODEL_PRICING\|annotate_cost\|llm_call" scripts/openlit_pipeline.py` → 0 совпадений
- [ ] `pricing.json` существует в корне проекта с ценами на используемые модели
- [ ] При запуске `gen_ai.usage.cost` на chat-span'ах **не равен 0** (проверить stdout-вывод)
- [ ] Опционально: при поднятом `phoenix serve` трейсы видны в UI на http://localhost:6006
- [ ] Опционально: cost в Phoenix UI отображается корректно для OpenRouter-модели с date-suffix (бывший stress-test)
- [ ] `ruff check .` проходит
- [ ] `AGENTS.md` (раздел Observability), `README.md` (tools-table), `BACKLOG.md`, `CHANGELOG.md` (`[0.3.0]`) — обновлены

---

## Известные ограничения

1. **`gen_ai.usage.cost = 0` для моделей вне `pricing.json`.** OpenLIT поставляет
   встроенную таблицу с ценами на популярные модели (OpenAI, Anthropic, Mistral,
   часть OpenRouter), но не покрывает date-suffix OpenRouter-маршруты. Решение —
   `pricing.json` (см. Custom pricing.json). Без файла стоимость не считается.

2. **`fetch_external_user` дублирует auto-instrumented urllib-span.** OpenLIT
   тянет `opentelemetry-instrumentation-urllib` как зависимость, поэтому
   `urllib.request.urlopen` сам эмитит `http.client.duration` /
   `http.client.response.size`. Ручной span нужен для **бизнес-контекста**
   (`url`, `user_id`, event `http_response` со status/body_bytes) — не для
   HTTP-метрик. Удалять ручной span не нужно.

3. **ConsoleSpanExporter дублирует вывод в Phoenix-режиме.** OpenLIT эмитит
   трейсы в OTLP (Phoenix), плюс наш ConsoleSpanExporter дополнительно в
   stdout. Для MVP это шум, но полезно при debugging; убрать легко —
   закомментировать блок `ConsoleSpanExporter` в `openlit_pipeline.py`.

4. **OpenLIT/OAI SDK дублируют HTTP-instrumentation на chat-вызовах.**
   OpenAI SDK использует httpx под капотом; OpenLIT instrument'ит OpenAI
   отдельно. Результат: на каждом chat-вызове два span'а — `chat <model>`
   (от OpenLIT) и `POST https://...` (от httpx). Сосуществуют нормально,
   но Phoenix показывает оба. Это by design OTel-stdlib'а.

---

## Дальше (BACKLOG)

- [ ] v0.3.0 — миграция на OpenLIT (этот документ)
- [ ] `ProjectPlan` (Flask → FastAPI) — следующий по BACKLOG.md
- [ ] Phoenix Experiments для A/B prompt testing
- [ ] SigNoz setup для полного APM
- [ ] Live Monitoring: token usage / cost / model distribution через Phoenix

---

## Связанные документы

- `docs/logfire_pipeline.md` — текущая версия (v0.2.0), будет archived как legacy
- `CHANGELOG.md` → `[0.2.0]` — почему ушли от Logfire
- `AGENTS.md` → раздел «Observability» — обновить правила под OpenLIT
- `BACKLOG.md` → добавить запись про v0.3.0
