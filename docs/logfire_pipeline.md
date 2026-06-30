# docs/logfire_pipeline.md

`scripts/logfire_pipeline.py` — сквозной pipeline с трассировкой через Logfire.

---

## Что умеет

На одном запуске прогоняет пять шагов и собирает их в один сквозной trace:

1. HTTP-запрос наружу (jsonplaceholder, через stdlib `urllib`).
2. Pydantic-валидация ответа.
3. In-memory lookup по внутреннему справочнику.
4. LLM-классификация запроса через OpenRouter + Instructor.
5. LLM-генерация финального ответа с учётом всего контекста.

В UI Logfire это видно как дерево span'ов: один корневой span и под ним дочерние — ручные (HTTP, lookup, LLM-обёртки) и автоматические (от `instrument_openai()` и `instrument_pydantic()`).

---

## Дерево trace'а

```
handle_user_request
├── fetch_external_user          ← ручной span (HTTP)
├── model_validate (User)        ← auto, instrument_pydantic
├── lookup_internal_data         ← ручной span
├── classify_intent
│   ├── chat.completion          ← auto, instrument_openai
│   └── model_validate (Intent)  ← auto, instrument_pydantic
└── generate_answer
    └── chat.completion          ← auto, instrument_openai
```

Auto-spans содержат model name, latency, input/output tokens и (если есть pricing data) стоимость. Manual spans содержат кастомные атрибуты — URL, user_id, длину ответа и т.п.

---

## Стек

- Python 3.11+
- Logfire
- OpenRouter (через OpenAI SDK)
- Instructor
- Pydantic v2
- urllib (stdlib, для HTTP)

Никакого LiteLLM, никакого ClickHouse, никакого Postgres. Logfire по дефолту пишет в локальный SQLite-файл (`.logfire/logfire.db`) — это вся инфра.

---

## Установка

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

`logfire` уже в `requirements.txt`.

---

## Конфигурация

Добавить в `.env` (скопируй из `.env.example`):

```text
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=openai/gpt-4o-mini
```

Без `OPENROUTER_API_KEY` шаги 4 и 5 упадут, но шаги 1–3 (HTTP, Pydantic, lookup) уже будут видны в трейсе.

`OPENROUTER_MODEL` опционален — дефолт `openai/gpt-4o-mini`. Можно поменять на любую модель, доступную через OpenRouter (`anthropic/claude-3.5-haiku`, `meta-llama/llama-3.1-70b-instruct`, и т.д.).

---

## Запуск

```powershell
python scripts\logfire_pipeline.py
```

---

## Просмотр трейсов: три режима

### Режим 1 — Только консоль (по дефолту, без сети)

Если `logfire auth login` не выполнялся и `LOGFIRE_TOKEN` не задан в env, скрипт выводит span'ы в stdout в Rich-формате. Дерево трейса видно прямо в терминале.

Без UI, без персистентности. Подходит для разовой проверки, что инструментация работает.

### Режим 2 — Logfire Cloud (рекомендуется, бесплатно)

В соседнем терминале:

```powershell
uv run logfire auth
```

> ⚠️ В Logfire 4.x команда именно `logfire auth` (без `login`),
> несмотря на то что `logfire auth --help` показывает только `logout`.
> Команда без подкоманды запускает OAuth device-flow.

Флоу:

1. Выбор региона (1=US, 2=EU) — интерактивно.
2. Enter — открывает браузер.
3. В браузере — device-code, подтверждение.
4. Токен сохраняется в `~/.logfire/default.toml`.

**После auth нужно создать проект** (иначе трейсы молча дропаются):

```powershell
.\venv\Scripts\logfire projects new my-ai-scripts
```

Список проектов: `.\venv\Scripts\logfire projects list`.
Сделать проект активным: `.\venv\Scripts\logfire projects use my-ai-scripts`.

После этого перезапусти скрипт — трейсы поедут в облако, UI на `https://logfire.pydantic.dev`.

Альтернатива — задать токен напрямую через env (если уже есть write-токен из web-UI):

```powershell
$env:LOGFIRE_TOKEN = "<your-write-token>"
```

Free tier: 1M observations/мес, retention 30 дней.

### Режим 3 — Свой OTLP-бэкенд (SigNoz / Jaeger / Honeycomb)

Logfire использует стандартный OpenTelemetry SDK, поэтому можно слать трейсы куда угодно. Перед запуском скрипта:

```powershell
$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:4318"
python scripts\logfire_pipeline.py
```

Самый лёгкий self-hosted вариант — SigNoz (single Docker Compose). Самый тяжёлый — Jaeger + зависимости. Для MVP overkill, но если Logfire Cloud не подходит по политикам — это путь.

---

## Что делает пример

### Шаг 1. `fetch_external_user`

Делает `GET https://jsonplaceholder.typicode.com/users/{user_id}`. Возвращает JSON. Логирует `status` и `body_bytes`.

Это ручной span — `logfire` не умеет auto-instrument `urllib.request` из stdlib (только сторонние HTTP-клиенты: httpx, requests, aiohttp). В реальном проекте, если перейдёшь на `httpx`, можно заменить ручной span на `logfire.instrument_httpx()`.

### Шаг 2. `validate_user`

`User.model_validate(raw)` — оборачивать вручную не нужно, `logfire.instrument_pydantic()` сам создаёт span. Видно:

- имя модели (`User`);
- входной dict (с санитизацией чувствительных полей);
- результат валидации (или `ValidationError` со списком ошибок).

### Шаг 3. `lookup_internal_data`

In-memory `dict` с тремя записями. Ручной span — имитация обращения к SQL/Redis. В атрибутах — `user_id`, в events — найденная запись.

### Шаг 4. `classify_intent`

OpenRouter + Instructor. Возвращает типизированный `Intent(query, action, target, confidence)`.

В trace попадают **три** span'а:

- `classify_intent` (ручной) — обёртка шага;
- `chat.completion` (auto, OpenAI) — сам LLM-вызов с prompt и completion;
- `model_validate` (auto, Pydantic) — валидация ответа модели через Instructor.

Это даёт полную картину: что отправили, что получили, как распарсили.

### Шаг 5. `generate_answer`

Сырой OpenAI client (без Instructor) — нам нужен свободный текст. В trace попадают два span'а:

- `generate_answer` (ручной);
- `chat.completion` (auto, OpenAI).

---

## Что показывает этот пример

✅ **Корневой span** — все шаги связываются в один trace. Без него дочерние span'ы существовали бы отдельно, и связь между ними пришлось бы восстанавливать вручную.

✅ **Auto-instrumentation работает через обёртки** — `logfire.instrument_openai()` ловит вызовы даже когда они проходят через `instructor.from_openai(...)`. Не нужно ничего дополнительно настраивать.

✅ **Ручные span'ы для нестандартных шагов** — HTTP через stdlib, in-memory lookup, бизнес-логика. `with logfire.span("name", **attrs)` и готово.

✅ **Атрибуты в span'ах** — `url`, `user_id`, `model`, `body_bytes`, `answer_length`. Их видно в UI без раскрытия span'а.

✅ **Cost-аннотация** — после каждого LLM-вызова скрипт считает стоимость по `MODEL_PRICING` и проставляет `genai.usage.cost` на span. Logfire Cloud рисует $ в UI. Без этой аннотации OpenRouter-модели показывают "Unknown", потому что Logfire не знает их pricing (`genai_prices` lookup падает на date-suffix).

✅ **Errors** — если шаг падает, span помечается как failed, exception логируется с типом и сообщением. Не нужно оборачивать в try/except руками (хотя `logfire.exception(...)` тоже есть).

✅ **Гибкость режима вывода** — `send_to_logfire="if-token-present"` (по дефолту): без токена работает локально (stdout), с токеном — в облако. Один скрипт работает в обоих режимах.

---

## Что показывает этот пример **не** показывает

❌ **Prompt Management в self-hosted** — в Logfire Cloud это есть (раздел Prompts в сайдбаре), но в self-hosted/open-source варианте — нет. Для self-hosted CMS промптов нужен Langfuse или своя морда поверх git.

❌ **Datasets / Experiments** — Logfire поддерживает это через `logfire.experiment()`, но в демо не показано (тема отдельного скрипта).

❌ **LLM-as-judge** — есть в Logfire, но не используется здесь.

---

## Сравнение с другими инструментами

| Что                  | Logfire                         | Langfuse                                              |
| -------------------- | ------------------------------- | ----------------------------------------------------- |
| Self-host сложность  | минимальная (SQLite-файл)       | высокая (ClickHouse + Postgres + Redis + S3 + Worker) |
| UI                   | `logfire web` (локально)        | web-приложение (Next.js)                              |
| OpenTelemetry-native | да (это его протокол)           | да (OTLP)                                             |
| Prompt CMS           | нет                             | да                                                    |
| Eval pipeline        | да (базовый)                    | да (богаче)                                           |
| Cloud-режим          | да (опционально, freemium)      | да (SaaS, есть enterprise)                            |
| Pricing              | бесплатно до 1M obs/мес в cloud | freemium + enterprise                                 |

---

## Дальше

- BACKLOG: следующий плановый tool — `ProjectPlan` (Flask → FastAPI).
- Идеи по улучшению этого скрипта:
  - заменить `urllib` на `httpx` + `logfire.instrument_httpx()` — убрать ручной span для HTTP;
  - добавить второй in-memory lookup с намеренной ошибкой — посмотреть, как выглядит failed span;
  - подключить `logfire.experiment()` — прогнать intent classification против фиксированного набора запросов.

---

## Честная ретроспектива (для будущих сессий)

Цель скрипта была — лёгкий drop-in трассировщик для MVP. По итогу:

| Что хотели                      | Что получили                                                          |
| ------------------------------- | --------------------------------------------------------------------- |
| Просто `pip install` и работает | `pip install` + auth + project create + custom pricing + manual spans |
| Локальный режим без облака      | Cloud-first; без токена только stdout, без UI                         |
| Cost tracking из коробки        | Ручная аннотация через OTel API (для OpenRouter)                      |
| Меньше операционки чем Langfuse | Сопоставимый overhead (просто в другой обёртке)                       |

**Для MVP, где важна простота, лучше рассмотреть:**

- `phoenix serve` (Arize) — open source, SQLite-режим, локальный web UI, OTel-native;
- structured JSON через stdlib `logging` + ad-hoc визуализация в Kibana/Grafana позже;
- OTLP → SigNoz (если готовы на Docker).

Logfire остаётся рабочим инструментом, но **как cloud-first решение с rich feature set** (Prompts CMS, Live Monitoring, Eval pipelines в Cloud), а не как лёгкий local-tracer.
