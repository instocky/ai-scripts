# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2026-06-30

### Added

- `scripts/parse_issue.py` — разбор bug-report в типизированный `Issue` (Enum `Priority`, вложенная модель `FileChange`, список файлов, `summary`, `estimated_hours`).
- `docs/parse_issue.md` — детальная документация скрипта.
- `README.md` — точка входа в проект: стек, быстрый старт, список tools.
- `BACKLOG.md` — что планируется добавить.

### Changed (parse_issue iteration)

- `scripts/parse_issue.py` — итерация по качеству вывода на малой модели:
  - добавлен `SYSTEM_PROMPT` с правилами маппинга файлов на причины и переписывания summary;
  - добавлен `Field(description=...)` на `reason` и `summary` (модель понимает, что туда писать);
  - добавлен `min_length=3` на `reason` (пустые строки падают на валидации);
  - добавлен `max_retries=3` в Instructor (структурные ошибки триггерят retry, реально сработал на первом прогоне — модель выдала dict вместо array).

## [0.1.0] - 2026-06-30

### Added

- `scripts/get_user.py` — первый пример: Instructor + Ollama извлекают `User(name, age, city)` из одного предложения.
- `requirements.txt` — `instructor`, `openai>=1.50.0`, `pydantic>=2.7`, `python-dotenv`.
- `.env.example` — шаблон для `OLLAMA_BASE_URL` / `OLLAMA_MODEL` / `OLLAMA_API_KEY`.
- `notes.md` — личный scratchpad автора.
