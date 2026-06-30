# docs/get_user.md

`scripts/get_user.py` — базовый сценарий Instructor + Ollama.

---

## Что умеет

На вход модели даётся одно предложение про пользователя. Instructor должен вернуть готовый объект `User`.

---

## Стек

- Python 3.11+
- Ollama
- Ornith
- Instructor
- OpenAI SDK
- Pydantic

---

## Установка

Создать виртуальное окружение:

```powershell
python -m venv venv
```

Активировать:

```powershell
.\venv\Scripts\activate
```

Установить зависимости:

```powershell
pip install -r requirements.txt
```

---

## requirements.txt

```text
instructor
openai>=1.50.0
pydantic>=2.7
python-dotenv
```

---

## Запуск Ollama

Пример API:

```bash
curl http://192.168.0.99:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model":"ornith:latest",
    "messages":[
      {
        "role":"user",
        "content":"Reply with exactly: pong"
      }
    ],
    "stream":false
  }'
```

OpenAI-совместимый endpoint:

```
http://192.168.0.99:11434/v1
```

---

## Запуск примера

```powershell
python scripts/get_user.py
```

---

## Что делает пример

Скрипт выполняет **два одинаковых запроса**.

### 1. Через OpenAI SDK

Получает сырой ответ модели.

Выводится:

- полный HTTP response;
- JSON, который реально вернула модель.

Например:

```json
{
  "reasoning": {
    ...
  }
}
```

или

```json
{
  "type": "message",
  "content": "..."
}
```

То есть модель отвечает так, как считает нужным.

### 2. Через Instructor

Используется схема:

```python
class User(BaseModel):
    name: str
    age: int
    city: str
```

Instructor самостоятельно:

- строит JSON Schema;
- инструктирует модель;
- извлекает нужные поля;
- валидирует ответ;
- возвращает готовый объект Python.

Результат:

```python
User(
    name='John',
    age=28,
    city='Miami'
)
```

---

## Пример вывода

```
======================================================================
RAW HTTP RESPONSE
======================================================================

{
   ...
}

======================================================================
RAW JSON FROM MODEL
======================================================================

{
    "reasoning": {
        ...
    }
}

======================================================================
PYDANTIC OBJECT
======================================================================

User(name='John', age=28, city='Miami')

======================================================================
MODEL_DUMP()
======================================================================

{
    "name": "John",
    "age": 28,
    "city": "Miami"
}
```

---

## Что показывает этот пример

Без Instructor приложение обычно делает:

```
LLM
    ↓
message.content
    ↓
json.loads()
    ↓
try/except
    ↓
ручная проверка
```

С Instructor цепочка выглядит так:

```
LLM
    ↓
Instructor
    ↓
Pydantic Validation
    ↓
User(...)
```

Разработчик сразу получает готовый типизированный объект и не занимается разбором JSON вручную.
