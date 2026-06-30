# scripts/parse_issue.py
#
# Разбор неструктурированного bug-report в типизированный объект Issue.
#
# Демонстрирует возможности Instructor поверх локальной Ollama-модели:
#   - Enum (Priority)
#   - вложенная модель (FileChange внутри Issue)
#   - список объектов (list[FileChange])
#   - автоматическое извлечение структуры из произвольного текста
#   - валидация через Pydantic (невалидные значения отсекаются)

import json
from enum import Enum

import instructor
from openai import OpenAI
from pydantic import BaseModel, Field


BASE_URL = "http://192.168.0.99:11434/v1"
MODEL = "ornith:latest"


# =====================================================
# Схема
# =====================================================

class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FileChange(BaseModel):
    path: str
    reason: str = Field(
        min_length=3,
        description=(
            "Why this specific file is affected, derived from the "
            "Suggested fix section. One short sentence."
        ),
    )


class Issue(BaseModel):
    title: str
    priority: Priority
    estimated_hours: int
    files: list[FileChange]
    summary: str = Field(
        description=(
            "One-sentence human summary of the bug, rephrased — "
            "not a verbatim copy of the Suggested fix section."
        ),
    )


# =====================================================
# Входные данные: сырой bug-report
# =====================================================

ISSUE_TEXT = """\
Bug report

The login page returns HTTP 500.

Priority: High

Affected files:
- auth.py
- login.py

Suggested fix:
Check database connection and session initialization.

Estimated effort: 3 hours.
"""

SYSTEM_PROMPT = """\
You extract structured information from a bug report.

Rules:
- title: short summary of the bug (one line).
- priority: one of "low", "medium", "high".
  Map Critical / Urgent / Blocker -> high, Normal -> medium,
  Minor / Trivial -> low.
- estimated_hours: integer hours. Strip units like "hours", "h", "hrs".
- files: for EACH path in "Affected files", derive `reason` from the
  "Suggested fix" text -- one short sentence explaining why THIS
  specific file is affected. Do not leave `reason` empty.
- summary: one-sentence human summary of the bug, REWRITTEN in your
  own words -- not a copy-paste of "Suggested fix".
"""

messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": ISSUE_TEXT},
]


# =====================================================
# 1. Обычный OpenAI клиент (сырой JSON от модели)
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
# 2. Instructor: валидация + типизированный объект
# =====================================================

client = instructor.from_openai(
    OpenAI(
        base_url=BASE_URL,
        api_key="ollama",
    ),
    mode=instructor.Mode.JSON,
)

issue = client.chat.completions.create(
    model=MODEL,
    response_model=Issue,
    messages=messages,
    max_retries=3,
)

print("\n" + "=" * 70)
print("PYDANTIC OBJECT")
print("=" * 70)

print(issue)

print("\n" + "=" * 70)
print("MODEL_DUMP()")
print("=" * 70)

print(json.dumps(
    issue.model_dump(),
    indent=2,
    ensure_ascii=False,
))

print("\n" + "=" * 70)
print("MODEL_DUMP_JSON()")
print("=" * 70)

print(issue.model_dump_json(indent=2))


# =====================================================
# 3. Доступ к полям как к обычному Python-объекту
# =====================================================

print("\n" + "=" * 70)
print("FIELD ACCESS")
print("=" * 70)

print(f"title:             {issue.title}")
print(f"priority:          {issue.priority} ({type(issue.priority).__name__})")
print(f"estimated_hours:   {issue.estimated_hours} ({type(issue.estimated_hours).__name__})")
print(f"summary:           {issue.summary}")
print(f"files ({len(issue.files)}):")
for f in issue.files:
    print(f"  - {f.path}: {f.reason}")