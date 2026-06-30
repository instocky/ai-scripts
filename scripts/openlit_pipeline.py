# scripts/openlit_pipeline.py
#
# Сквозной pipeline с трассировкой через OpenLIT + OpenTelemetry.
#
# Демонстрирует:
#   - HTTP-запрос наружу (urllib, stdlib) — ручной span
#   - Pydantic-валидацию (auto-instrumented от OpenLIT)
#   - in-memory lookup — ручной span
#   - LLM-вызов #1 через OpenRouter + Instructor — auto + manual span
#   - LLM-вызов #2 — auto + manual span
#   - корневой span связывает все шаги в один trace
#
# Дерево в Phoenix UI (или в stdout-формате от ConsoleSpanExporter):
#   handle_user_request
#     ├── fetch_external_user        (manual OTel span)
#     ├── model_validate             (auto, от OpenLIT)
#     ├── lookup_internal_data       (manual OTel span)
#     ├── classify_intent            (manual OTel span)
#     │     ├── chat {model=...}     (auto, от OpenLIT)
#     │     └── model_validate       (auto, от OpenLIT)
#     └── generate_answer            (manual OTel span)
#           └── chat {model=...}     (auto, от OpenLIT)
#
# Запуск:
#   python scripts\openlit_pipeline.py
#     → stdout (default, ConsoleSpanExporter).
#
#   С Phoenix (опционально):
#     phoenix serve
#     $env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:6006"
#     python scripts\openlit_pipeline.py
#     → http://localhost:6006

import json
import os
import urllib.request
from pathlib import Path
from typing import Literal

import instructor
import openlit
from dotenv import load_dotenv
from openai import OpenAI
from opentelemetry import trace
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from pydantic import BaseModel, Field


load_dotenv()


# =====================================================
# 1. OpenLIT + OpenTelemetry init
# =====================================================
#
# Режимы:
#   - default (без OTEL_EXPORTER_OTLP_ENDPOINT):
#       OpenLIT ставит no-op OTLP, мы добавляем ConsoleSpanExporter
#       → трейсы идут в stdout (JSON через OTel SDK).
#   - OTEL_EXPORTER_OTLP_ENDPOINT=http://... :
#       OpenLIT ставит OTLP HTTP exporter на этот endpoint
#       → Phoenix UI / SigNoz / Logfire Cloud (escape hatch).
#
# Phoenix setup:
#   phoenix serve
#   $env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:6006"
#   python scripts\openlit_pipeline.py

# Custom pricing: OpenLIT поставляет pricing.json с ценами на популярные модели
# (OpenAI, Anthropic, часть OpenRouter), но для моделей с date-suffix (например
# z-ai/glm-5.2-20260616) lookup возвращает 0 — нужно подсунуть свой JSON.
# Формат: {category: {model_name: {promptPrice, completionPrice}}} в USD за 1K токенов.
# Override через env OPENLIT_PRICING_JSON (URL или file path).
#
# ⚠️ ВАЖНО: на Windows НИ ОДИН path/URL формат не работает через параметр
# `pricing_json=` из-за бага в OpenLIT 1.42.1 (см. memory: pricing-on-windows).
# Краткая суть: `fetch_pricing_info()` использует `urlparse(path).scheme != ""`
# для определения URL-это или путь. На Windows `urlparse("C:\...").scheme == "c"`
# (драйв = scheme), и `requests.get("c:...")` молча падает → pricing_info = {}.
# То же с `file:///C:/...` — `requests` не умеет `file://` без requests-file.
# Поэтому читаем файл сами и monkey-patch'им `openlit.fetch_pricing_info` —
# он импортируется как имя в openlit.__init__, патч этого имени перехватывает
# вызов из `init()`.
_PRICING_JSON_DEFAULT = Path(__file__).resolve().parent.parent / "pricing.json"
_pricing_json_path = Path(os.getenv("OPENLIT_PRICING_JSON") or _PRICING_JSON_DEFAULT)
if _pricing_json_path.exists():
    with open(_pricing_json_path, encoding="utf-8") as f:
        _custom_pricing_dict = json.load(f)

    def _patched_fetch_pricing_info(pricing_json=None):  # noqa: ARG001
        # Аргумент pricing_json игнорируем — у нас уже загруженный dict.
        return _custom_pricing_dict

    # Патчим в обоих namespace (openlit/__init__.py импортирует функцию через
    # `from openlit.__helpers import fetch_pricing_info` — локальный binding).
    import openlit
    openlit.fetch_pricing_info = _patched_fetch_pricing_info
    print(
        f"[openlit] custom pricing loaded from {_pricing_json_path}: "
        f"{len(_custom_pricing_dict.get('chat', {}))} chat models",
    )
else:
    print(
        f"[openlit] WARNING: pricing_json not found at {_pricing_json_path}, "
        "using built-in defaults. cost for unknown models will be 0.",
    )

openlit.init(
    otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
    pricing_json=None,  # ignored by patched fetch_pricing_info
)

# ConsoleSpanExporter — для stdout-режима (полезно и для дев, и для CI).
# В Phoenix-режиме работает параллельно с OTLP — вывод будет двойной,
# но это приемлемо для MVP.
_provider = trace.get_tracer_provider()
_real_provider = getattr(_provider, "_real_provider", _provider) or _provider
if hasattr(_real_provider, "add_span_processor"):
    _real_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

tracer = trace.get_tracer(__name__)


# =====================================================
# 2. Config
# =====================================================

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# Single shared OpenAI client. OpenLIT auto-instruments OpenAI на уровне
# класса — каждый вызов chat.completions.create создаёт OTel-span с model /
# tokens / cost (через встроенные price-таблицы OpenLIT).
_openai_client = OpenAI(
    base_url=OPENROUTER_BASE_URL,
    api_key=OPENROUTER_API_KEY,
)

# Instructor-обёртка для Pydantic-валидации ответов.
# В Logfire-версии пришлось уйти от Instructor ради доступа к usage —
# с OpenLIT usage доступен через OTel-атрибуты, считать вручную не нужно.
_instructor_client = instructor.from_openai(_openai_client)


# =====================================================
# 3. Schema
# =====================================================

class User(BaseModel):
    id: int
    name: str
    username: str
    email: str
    company: str | None = None


class Intent(BaseModel):
    """Извлечённый из свободного запроса интент."""

    query: str = Field(description="Original user query, verbatim")
    action: Literal["fetch", "summarize", "transform", "unknown"] = Field(
        description="What the user wants to do with the data",
    )
    target: str = Field(
        description="Subject of the action (e.g. 'user:42', 'all users')",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Model self-rated confidence in classification",
    )


class PipelineResult(BaseModel):
    user: User
    internal: dict
    intent: Intent
    answer: str


# =====================================================
# 4. Pipeline steps — каждый шаг в своём span
# =====================================================

def fetch_external_user(user_id: int) -> dict:
    """Шаг 1: HTTP-запрос наружу через stdlib urllib.

    OTel SDK не auto-instrument urllib из stdlib (только сторонние клиенты
    вроде httpx / requests), поэтому оборачиваем вручную.
    """
    url = f"https://jsonplaceholder.typicode.com/users/{user_id}"
    with tracer.start_as_current_span(
        "fetch_external_user",
        attributes={"url": url, "user_id": user_id},
    ) as span:
        with urllib.request.urlopen(url, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            span.add_event(
                "http_response",
                attributes={"status": resp.status, "body_bytes": len(raw)},
            )
            return json.loads(raw)


def validate_user(raw: dict) -> User:
    """Шаг 2: Pydantic-валидация.

    OpenLIT в init() auto-instruments Pydantic — этот вызов сам создаст span
    со структурой модели и любыми ошибками валидации.

    jsonplaceholder отдаёт company как dict — берём только name.
    """
    if isinstance(raw.get("company"), dict):
        raw = {**raw, "company": raw["company"].get("name")}
    return User.model_validate(raw)


def lookup_internal_data(user: User) -> dict:
    """Шаг 3: in-memory lookup. Имитация обращения к локальному справочнику.

    В реальном проекте тут будет SQL / Redis / что-то ещё — суть одна:
    ручной span вокруг операции, чтобы видеть её в трейсе.
    """
    store = {
        1: {"tier": "pro", "region": "eu", "notes": "early adopter"},
        2: {"tier": "free", "region": "us"},
        3: {"tier": "pro", "region": "apac", "notes": "needs follow-up"},
    }
    with tracer.start_as_current_span(
        "lookup_internal_data",
        attributes={"user_id": user.id},
    ) as span:
        data = store.get(user.id, {"tier": "free", "region": "unknown"})
        span.add_event("internal_record", attributes=data)
        return data


def classify_intent(query: str) -> Intent:
    """Шаг 4: LLM-классификация запроса через OpenRouter + Instructor.

    OpenLIT auto-instruments OpenAI SDK. Instructor оборачивает client, но
    базовый chat.completions.create остаётся видимым OpenLIT'у — span с
    model / tokens / cost генерируется автоматически (важно: проверить
    эмпирически, что cost-атрибут попадает на chat-completion span, а не
    на родительский — это основной stress-test миграции).
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You classify user intent from a free-form query. "
                "Pick action from: fetch, summarize, transform, unknown. "
                "Return strict JSON with fields: query (str), action (str), "
                "target (str), confidence (number 0..1)."
            ),
        },
        {"role": "user", "content": query},
    ]
    with tracer.start_as_current_span(
        "classify_intent",
        attributes={"query": query},
    ):
        return _instructor_client.chat.completions.create(
            model=OPENROUTER_MODEL,
            response_model=Intent,
            messages=messages,
        )


def generate_answer(user: User, intent: Intent, internal: dict) -> str:
    """Шаг 5: финальный LLM-вызов с учётом всего контекста."""
    messages = [
        {
            "role": "system",
            "content": "You answer concisely based on provided context.",
        },
        {
            "role": "user",
            "content": (
                f"User: {user.name} (id={user.id}, company={user.company})\n"
                f"Internal record: {internal}\n"
                f"User query: {intent.query}\n"
                f"Classified intent: {intent.action} on {intent.target}\n\n"
                "Answer in 1-2 sentences."
            ),
        },
    ]
    with tracer.start_as_current_span("generate_answer"):
        resp = _openai_client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=messages,
        )
        return resp.choices[0].message.content or ""


# =====================================================
# 5. Main pipeline
# =====================================================

def run_pipeline(user_id: int, query: str) -> PipelineResult:
    """Корневой span связывает все шаги в один trace."""
    with tracer.start_as_current_span(
        "handle_user_request",
        attributes={"user_id": user_id, "query": query},
    ) as root:
        raw = fetch_external_user(user_id)
        user = validate_user(raw)
        internal = lookup_internal_data(user)
        intent = classify_intent(query)
        answer = generate_answer(user, intent, internal)
        root.set_attribute("answer_length", len(answer))
    return PipelineResult(user=user, internal=internal, intent=intent, answer=answer)


# =====================================================
# 6. Entry point
# =====================================================

if __name__ == "__main__":
    if not OPENROUTER_API_KEY:
        print(
            "[!] OPENROUTER_API_KEY не задан.\n"
            "    Добавь в .env:\n"
            "      OPENROUTER_API_KEY=sk-or-v1-...\n"
            "      OPENROUTER_MODEL=openai/gpt-4o-mini  # опционально\n\n"
            "    Без ключа шаги LLM (4 и 5) упадут, но шаги 1–3\n"
            "    (HTTP, Pydantic, lookup) уже будут видны в трейсе."
        )

    print("=" * 70)
    print("PIPELINE START")
    print("=" * 70)

    try:
        result = run_pipeline(
            user_id=1,
            query="Tell me about Leanne's account tier and region.",
        )
        print("\n" + "=" * 70)
        print("RESULT")
        print("=" * 70)
        print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"\n[!] Pipeline failed: {type(e).__name__}: {e}")

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)
    print("Трейсы:")
    print("  • default — выше в stdout (ConsoleSpanExporter);")
    print("  • Phoenix — phoenix serve + $env:OTEL_EXPORTER_OTLP_ENDPOINT='http://localhost:6006'")
    print("  • UI: http://localhost:6006")