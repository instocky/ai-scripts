# 0630_ai-scripts

Сборник AI-tools — небольших скриптов, демонстрирующих разные аспекты работы с LLM: структурный вывод, парсинг неструктурированного текста, планирование изменений.

Базовый стек — **Instructor + Ollama + Pydantic v2**. Ollama отдаёт OpenAI-совместимый API, Instructor строит JSON Schema из Pydantic-модели, валидирует ответ и возвращает готовый типизированный объект.

---

## Стек

- Python 3.11+
- Ollama (локальный inference)
- Instructor
- OpenAI SDK (Ollama OpenAI-compatible endpoint)
- Pydantic v2

---

## Быстрый старт

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

Скопировать `.env.example` в `.env` и заполнить при необходимости:

```text
OLLAMA_BASE_URL=http://192.168.0.99:11434/v1
OLLAMA_MODEL=ornith:latest
OLLAMA_API_KEY=ollama
```

Запуск любого скрипта:

```powershell
python scripts\<script_name>.py
```

---

## Tools

Скрипты добавляются по мере проработки тем. Каждый идёт с детальным описанием в `docs/`.

| #   | Скрипт                      | Пакет                                                                                                       | Что демонстрирует                                                                                            | Документация                                   |
| --- | --------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | ---------------------------------------------- |
| 1   | `scripts/get_user.py`       | [Instructor](https://pypi.org/project/instructor/)                                                          | Базовый сценарий: Instructor извлекает `User(name, age, city)` из одного предложения                         | [docs/get_user.md](docs/get_user.md)           |
| 2   | `scripts/parse_issue.py`    | [Instructor](https://pypi.org/project/instructor/)                                                          | Enum + вложенная модель + список + валидация + retries на малой модели                                       | [docs/parse_issue.md](docs/parse_issue.md)     |
| 3   | `scripts/logfire_pipeline.py` | [Logfire](https://pydantic.dev/logfire) + [OpenRouter](https://openrouter.ai/) через OpenAI SDK + Instructor | Сквозной pipeline с трассировкой: HTTP → Pydantic → lookup → LLM ×2. Локальный SQLite, без облака              | [docs/logfire_pipeline.md](docs/logfire_pipeline.md) |

---

## Planned

См. [BACKLOG.md](BACKLOG.md) — что планируется добавить следующим.

---

## Дополнительно

- [CHANGELOG.md](CHANGELOG.md) — что менялось в проекте.
- `notes.md` — личный scratchpad автора (не часть документации проекта).
