# Backlog

Простой список того, что планируется добавить. Порядок ≈ приоритет.

## Next

- [ ] **ProjectPlan** (`scripts/plan_migration.py`) — следующий шаг после `parse_issue`. На вход — свободный промпт про миграцию проекта (например, Flask → FastAPI + uv + Docker + pytest), на выход — `ProjectPlan(summary, commands, edits, risks)`. Демонстрирует, как Instructor раскладывает команды / правки / риски — то, что похоже на возврат современных coding-агентов (Codex, OpenCode).

## Ideas

- [ ] **Phoenix Experiments** — A/B prompt testing через Phoenix UI для сравнения вариантов `SYSTEM_PROMPT` и моделей.
- [ ] **SigNoz setup** — Docker Compose с SigNoz для full APM (traces + metrics + logs + alerts) в одном self-hosted стеке.
- [ ] **Live Monitoring dashboard** — token usage / cost / model distribution через Phoenix или SigNoz после каждого прогона pipeline.
- [ ] Попробовать более крупную модель на Ollama (qwen2.5:14b, llama3.1:8b) — Ornith на структурных задачах ошибается (dict вместо array, пустые поля). Более крупные модели должны справляться без `max_retries`.
- [ ] Добавить few-shot пример в `SYSTEM_PROMPT` для малых моделей — стабилизирует формат вывода на задачах с гибкой структурой.
- [ ] Прогон `parse_issue.py` на негативных кейсах — bug-report с `priority: urgent`, без секции `Estimated effort`, с пустым `Affected files`. Проверить, что валидация корректно отрабатывает.

## Done

- [x] **OpenLIT pipeline** (`scripts/openlit_pipeline.py`, v0.3.0, 2026-06-30) — миграция сквозного pipeline-трейсинга с Logfire Cloud на OpenLIT + OpenTelemetry + Phoenix (опционально). Тот же сценарий (HTTP → Pydantic → lookup → LLM ×2), без workarounds (`MODEL_PRICING`, `annotate_cost`, `llm_call`, custom spans). Дефолтный backend — stdout, Phoenix через `OTEL_EXPORTER_OTLP_ENDPOINT`. План и acceptance criteria — [docs/openlit_pipeline.md](docs/openlit_pipeline.md).
