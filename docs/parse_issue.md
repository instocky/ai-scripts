# docs/parse_issue.md

`scripts/parse_issue.py` — разбор неструктурированного bug-report в типизированный объект `Issue`.

---

## Что умеет

На вход модели даётся обычный текст bug-report (свободная форма: заголовок, приоритет, список файлов, suggested fix, оценка времени). Instructor должен вернуть готовый объект `Issue` с вложенной моделью `FileChange`, Enum `Priority` и списком файлов.

---

## Схема

```python
from enum import Enum
from pydantic import BaseModel, Field


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
```

---

## Входные данные

```python
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
```

---

## Стек

- Python 3.11+
- Ollama
- Ornith
- Instructor
- OpenAI SDK
- Pydantic v2

---

## Установка

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

---

## Запуск Ollama

OpenAI-совместимый endpoint:

```
http://192.168.0.99:11434/v1
```

---

## Запуск примера

```powershell
python scripts/parse_issue.py
```

---

## Что делает пример

Скрипт выполняет **один и тот же запрос дважды**.

### 1. Через OpenAI SDK (сырой JSON)

Получает сырой ответ модели. Выводится полный HTTP response и JSON, который реально вернула модель. **Никакой валидации нет** — то, что пришло, то и пришло.

На первой попытке Ornith может выдать что-то вроде:

```json
{
  "type": "functionCall",
  "function": "search_file",
  "arguments": {
    "query": "auth.py",
    "path": ["/Users/lincoln/workspace/project-archery"]
  }
}
```

То есть coding-модель любит выдавать tool-calls вместо прямого ответа даже на структурных задачах.

### 2. Через Instructor

Instructor:

- строит JSON Schema из `Issue`;
- шлёт системный промпт с правилами маппинга;
- извлекает JSON из ответа модели;
- валидирует каждое поле через Pydantic;
- при `ValidationError` повторяет запрос до `max_retries` раз, подсовывая модели сообщение об ошибке;
- возвращает готовый типизированный объект `Issue`.

---

## System prompt

```python
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
```

---

## Пример вывода

```
======================================================================
PYDANTIC OBJECT
======================================================================

title='Login page crashes with HTTP 500 error' priority=<Priority.HIGH: 'high'> estimated_hours=3 files=[FileChange(path='auth.py', reason='Authentication module likely has a session initialization or database connectivity issue contributing to the 500 error.'), FileChange(path='login.py', reason='Login handler depends on proper database connection setup, which fails and triggers the HTTP 500 response.')] summary='The login page crashes with an internal server error due to faulty database connectivity or session management in authentication modules.'

======================================================================
FIELD ACCESS
======================================================================

title:             Login page crashes with HTTP 500 error
priority:          Priority.HIGH (Priority)
estimated_hours:   3 (int)
summary:           The login page crashes with an internal server error due to faulty database connectivity or session management in authentication modules.
files (2):
  - auth.py: Authentication module likely has a session initialization or database connectivity issue contributing to the 500 error.
  - login.py: Login handler depends on proper database connection setup, which fails and triggers the HTTP 500 response.
```

---

## Что показывает этот пример

✅ **Enum** — `priority` нормализован в `Priority.HIGH`. Если модель вернёт `"urgent"` или `"critical"`, Pydantic выкинет `ValidationError` ещё до возврата объекта.

✅ **Вложенная модель** — `FileChange` живёт внутри `Issue.files`, не отдельной плоской структурой.

✅ **Список объектов** — `list[FileChange]`, валидация каждого элемента отдельно.

✅ **Integer coercion** — модель вернула `"3 hours"` в прозе, Instructor извлёк `estimated_hours=3` как чистый `int`.

✅ **Преобразование текста в структуру** — свободный bug-report → готовый Pydantic-объект.

✅ **Автоматическая валидация** — `min_length=3` на `reason`, Enum на `priority`. Невалидные значения не проходят.

✅ **`max_retries`** — реально задействован на первом прогоне: модель выдала `files` как dict (не array), Instructor поймал `ValidationError`, перезапросил, получил правильную форму.

---

## Итерация: что было → что сделали → что получилось

### Что было (первый прогон)

- `reason=''` для обоих файлов — модель не связала файлы с "Suggested fix".
- `summary` — копипаста из "Suggested fix".
- `files` — на первой попытке dict вместо array, скрипт упал бы без `max_retries`.

### Что сделали

1. Добавили `SYSTEM_PROMPT` с явными правилами маппинга файлов на причины и переписывания summary.
2. Добавили `Field(description=...)` на `reason` и `summary` — модель получает описание поля в JSON Schema.
3. Добавили `min_length=3` на `reason` — пустые строки теперь падают на валидации, что триггерит retry.
4. Добавили `max_retries=3` в Instructor — структурные ошибки (dict vs array) автоматически перевыпускаются.

### Что получилось

- `reason` заполнены осмысленно (Database connection / session initialization).
- `summary` переписан, не копипаста.
- `max_retries` реально сработал — первая попытка вернула dict, вторая — правильный array.

Подробности в `CHANGELOG.md` → `[0.1.1]`.

---

## Дальше

- См. [BACKLOG.md](../BACKLOG.md) — следующий плановый tool: `ProjectPlan` (Flask → FastAPI).
- Текущие ограничения Ornith (coding-модель на структурных задачах): см. `BACKLOG.md` → Ideas.
