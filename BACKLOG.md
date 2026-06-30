# Backlog

Простой список того, что планируется добавить. Порядок ≈ приоритет.

## Next

- [ ] **ProjectPlan** (`scripts/plan_migration.py`) — следующий шаг после `parse_issue`. На вход — свободный промпт про миграцию проекта (например, Flask → FastAPI + uv + Docker + pytest), на выход — `ProjectPlan(summary, commands, edits, risks)`. Демонстрирует, как Instructor раскладывает команды / правки / риски — то, что похоже на возврат современных coding-агентов (Codex, OpenCode).

## Ideas

- [ ] Попробовать более крупную модель на Ollama (qwen2.5:14b, llama3.1:8b) — Ornith на структурных задачах ошибается (dict вместо array, пустые поля). Более крупные модели должны справляться без `max_retries`.
- [ ] Добавить few-shot пример в `SYSTEM_PROMPT` для малых моделей — стабилизирует формат вывода на задачах с гибкой структурой.
- [ ] Прогон `parse_issue.py` на негативных кейсах — bug-report с `priority: urgent`, без секции `Estimated effort`, с пустым `Affected files`. Проверить, что валидация корректно отрабатывает.

## Done

_(пока пусто)_
