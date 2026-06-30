# scripts/logfire_pipeline.py
#
# Сквозной pipeline с трассировкой через Logfire.
#
# Демонстрирует:
#   - HTTP-запрос наружу (urllib, stdlib)
#   - кастомный span для преобразования
#   - Pydantic-валидацию (auto-instrumented)
#   - in-memory lookup в ручном span
#   - LLM-вызов через OpenRouter + Instructor
#   - второй LLM-вызов с учётом всего контекста
#   - корневой span связывает все шаги в один trace
#
# В UI Logfire это выглядит как дерево:
#   handle_user_request
#     ├── fetch_external_user      (HTTP, stdlib urllib)
#     ├── model_validate           (auto, от instrument_pydantic)
#     ├── lookup_internal_data     (in-memory store)
#     ├── classify_intent
#     │     ├── chat.completion    (auto, от instrument_openai)
#     │     └── model_validate     (auto, от instrument_pydantic)
#     └── generate_answer
#           └── chat.completion    (auto, от instrument_openai)
#
# Запуск:
#   python scripts/logfire_pipeline.py
#   logfire web          # в соседнем терминале — UI на http://localhost:7000

import json
import os
import urllib.request
from typing import Literal

import logfire
from dotenv import load_dotenv
from openai import OpenAI
from opentelemetry import trace
from pydantic import BaseModel, Field


load_dotenv()


# =====================================================
# 1. Logfire configuration
# =====================================================
#
# Режимы Logfire 4.x:
#   - send_to_logfire="if-token-present" (по дефолту):
#       без токена → только Rich-вывод в stdout (без UI, без сети);
#       с токеном  → отправляет в Logfire Cloud (https://logfire.pydantic.dev).
#   - send_to_logfire=False: только stdout, никогда в облако.
#   - send_to_logfire=True: всегда в облако (упадёт без токена).
#
# Чтобы включить UI, выполни `logfire auth login` — токен сохранится в
# ~/.logfire/default.toml и будет подхватываться автоматически.
#
# Для других OTLP-бэкендов (SigNoz, Jaeger, Honeycomb) выстави
# переменную окружения OTEL_EXPORTER_OTLP_ENDPOINT — Logfire использует
# стандартный OTel SDK под капотом.

logfire.configure(
    send_to_logfire="if-token-present",
    inspect_arguments=True,
)

# Auto-instrumentation:
# - Pydantic — каждая .model_validate попадает в трейс со структурой
#   модели и любыми ошибками валидации.
#
# - OpenAI SDK НЕ инструментируем автоматически: делаем Chat Completion
#   span вручную через llm_call(), чтобы можно было проставить cost на
#   тот же span (auto-instrument закрывает span ДО нашего annotate_cost).
logfire.instrument_pydantic()


# =====================================================
# 2. Config
# =====================================================

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# Pricing in $/M tokens (input, output).
# Logfire не знает OpenRouter-модели (нет в genai_prices), поэтому
# считаем стоимость сами и проставляем на span как genai.usage.cost.
# Источник цен: https://openrouter.ai/models/<model>
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # model substring   -> (input $/M, output $/M)
    "z-ai/glm-5.2": (0.94, 3.00),       # Z.ai GLM 5.2, 2026-06-16, 1M context
    "openai/gpt-4o-mini": (0.15, 0.60),  # дефолт, на случай переключения
}


def annotate_cost(model: str, usage) -> None:
    """Считает и проставляет genai.usage.cost на текущий span.

    Вызывать сразу после OpenAI-вызова, пока span ещё открыт.
    Logfire читает этот атрибут и рисует стоимость в UI.
    """
    if not usage:
        return
    pricing = next(
        (p for key, p in MODEL_PRICING.items() if key in model),
        None,
    )
    if not pricing:
        return
    input_price, output_price = pricing
    input_cost = usage.prompt_tokens * input_price / 1_000_000
    output_cost = usage.completion_tokens * output_price / 1_000_000
    total = input_cost + output_cost
    span = trace.get_current_span()
    span.set_attribute("genai.usage.input_cost", input_cost)
    span.set_attribute("genai.usage.output_cost", output_cost)
    span.set_attribute("genai.usage.cost", total)
    logfire.info(
        "cost_calculated",
        model=model,
        input_tokens=usage.prompt_tokens,
        output_tokens=usage.completion_tokens,
        cost_usd=total,
    )


def llm_call(
    messages: list[dict],
    *,
    span_name: str,
    json_mode: bool = False,
) -> object:
    """OpenAI-вызов внутри ручного Chat Completion span.

    Почему вручную, а не через logfire.instrument_openai():
    auto-instrument закрывает Chat Completion span ДО того, как мы
    успеваем проставить cost на него (мы оказываемся в родительском
    span, и set_attribute уходит не туда). Ручной span = полный контроль.

    Возвращает OpenAI ChatCompletion response.
    """
    with logfire.span(span_name, model=OPENROUTER_MODEL) as span:
        client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=OPENROUTER_API_KEY,
        )
        resp = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=messages,
            response_format={"type": "json_object"} if json_mode else None,
        )
        if resp.usage:
            span.set_attribute("genai.usage.input_tokens", resp.usage.prompt_tokens)
            span.set_attribute("genai.usage.output_tokens", resp.usage.completion_tokens)
            annotate_cost(OPENROUTER_MODEL, resp.usage)
        # Логируем полные messages/completion как events (rich attributes).
        span.set_attribute("genai.prompt.messages", json.dumps(messages, ensure_ascii=False))
        if resp.choices:
            completion = resp.choices[0].message.content or ""
            span.set_attribute("genai.completion.content", completion)
        return resp


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

    Logfire не умеет auto-instrument urllib из stdlib (только сторонние
    HTTP-клиенты вроде httpx / requests), поэтому оборачиваем вручную.
    """
    url = f"https://jsonplaceholder.typicode.com/users/{user_id}"
    with logfire.span("fetch_external_user", url=url, user_id=user_id):
        with urllib.request.urlopen(url, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            logfire.info("http_response", status=resp.status, body_bytes=len(raw))
            return json.loads(raw)


def validate_user(raw: dict) -> User:
    """Шаг 2: Pydantic-валидация.

    Благодаря `logfire.instrument_pydantic()` этот вызов сам создаст span
    со структурой модели и входными данными. Ошибки валидации тоже
    логируются — без ручной обёртки.

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
    with logfire.span("lookup_internal_data", user_id=user.id):
        data = store.get(user.id, {"tier": "free", "region": "unknown"})
        logfire.info("internal_record", **data)
        return data


def classify_intent(query: str) -> Intent:
    """Шаг 4: LLM-классификация запроса через OpenRouter.

    Chat Completion span делаем вручную (через llm_call), чтобы cost
    попал на правильный span. Pydantic-валидация через model_validate_json
    даст auto-span от instrument_pydantic.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You classify user intent from a free-form query. "
                "Pick action from: fetch, summarize, transform, unknown. "
                'Return strict JSON with fields: query (str), action (str), '
                'target (str), confidence (number 0..1).'
            ),
        },
        {"role": "user", "content": query},
    ]
    with logfire.span("classify_intent"):
        resp = llm_call(messages, span_name="chat_completion_classify", json_mode=True)
        return Intent.model_validate_json(resp.choices[0].message.content)


def generate_answer(user: User, intent: Intent, internal: dict) -> str:
    """Шаг 5: финальный LLM-вызов с учётом всего контекста.

    Chat Completion span — вручную (через llm_call), чтобы cost попал
    на правильный span. Возвращаем свободный текст.
    """
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
    with logfire.span("generate_answer"):
        resp = llm_call(messages, span_name="chat_completion_generate")
        return resp.choices[0].message.content or ""


# =====================================================
# 5. Main pipeline
# =====================================================

def run_pipeline(user_id: int, query: str) -> PipelineResult:
    """Корневой span связывает все шаги в один trace."""
    with logfire.span("handle_user_request", user_id=user_id, query=query) as root:
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
        logfire.exception("pipeline_failed")
        print(f"\n[!] Pipeline failed: {type(e).__name__}: {e}")

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)
    print("Трейсы:")
    print("  • локально — выше в stdout (Rich-формат);")
    print("  • облако  — https://logfire-us.pydantic.dev/irvicon/starter-project/live")