# scripts/get_user.py

import json

import instructor
from openai import OpenAI
from pydantic import BaseModel


BASE_URL = "http://192.168.0.99:11434/v1"
MODEL = "ornith:latest"


class User(BaseModel):
    name: str
    age: int
    city: str


messages = [
    {
        "role": "user",
        "content": "John is 28 years old and lives in Miami.",
    }
]


# =====================================================
# 1. Обычный OpenAI клиент (сырой ответ)
# =====================================================

raw_client = OpenAI(
    base_url=BASE_URL,
    api_key="ollama",
)

raw_response = raw_client.chat.completions.create(
    model=MODEL,
    messages=messages,
    response_format={"type": "json_object"},
)

print("\n" + "=" * 70)
print("RAW HTTP RESPONSE")
print("=" * 70)

print(json.dumps(raw_response.model_dump(), indent=2, ensure_ascii=False))

raw_json = raw_response.choices[0].message.content

print("\n" + "=" * 70)
print("RAW JSON FROM MODEL")
print("=" * 70)

print(raw_json)


# =====================================================
# 2. Instructor
# =====================================================

client = instructor.from_openai(
    OpenAI(
        base_url=BASE_URL,
        api_key="ollama",
    ),
    mode=instructor.Mode.JSON,
)

user = client.chat.completions.create(
    model=MODEL,
    response_model=User,
    messages=messages,
)

print("\n" + "=" * 70)
print("PYDANTIC OBJECT")
print("=" * 70)

print(user)

print("\n" + "=" * 70)
print("MODEL_DUMP()")
print("=" * 70)

print(json.dumps(
    user.model_dump(),
    indent=2,
    ensure_ascii=False,
))

print("\n" + "=" * 70)
print("MODEL_DUMP_JSON()")
print("=" * 70)

print(user.model_dump_json(indent=2))