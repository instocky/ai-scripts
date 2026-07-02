# Crawler Tasks

Чеклист атомарных задач для реализации MVP crawler. Документ предназначен для пошагового закрытия работ по мере написания кода.

Связанные документы:

- [crawler_implementation_spec_v1.md](C:\Projects\Python\0630_ai-scripts\docs\crawler_implementation_spec_v1.md)
- [crawler_implementation_plan.md](C:\Projects\Python\0630_ai-scripts\docs\crawler_implementation_plan.md)

---

## Foundation

- [x] Создать пакет `src/crawler/`
- [x] Добавить `src/crawler/__init__.py`
- [x] Создать `src/crawler/models.py`
- [x] Добавить `CrawlConfig`
- [x] Добавить `CrawledPage`
- [x] Добавить `RunStats`
- [x] Добавить `RunManifest`
- [x] Добавить `CrawlRunResult`
- [x] Создать `src/crawler/url_utils.py`
- [x] Реализовать `normalize_url()`
- [x] Реализовать same-domain filtering
- [x] Реализовать преобразование URL в путь внутри `pages/`

---

## Crawl Client

- [x] Создать `src/crawler/client.py`
- [x] Добавить `Crawl4AiClient`
- [x] Изолировать импорт `crawl4ai` внутри `client.py`
- [x] Реализовать crawl одной страницы
- [x] Извлекать `title`
- [x] Извлекать `markdown`
- [x] Извлекать ссылки для дальнейшего обхода
- [x] Добавить структурированную обработку ошибок client-слоя

---

## Storage

- [x] Создать `src/crawler/storage.py`
- [x] Добавить `MarkdownStorage`
- [x] Реализовать создание каталога прогона
- [x] Реализовать структуру `output/<domain>/<timestamp>/pages/`
- [x] Реализовать запись markdown-файлов
- [x] Добавить YAML front matter
- [x] Реализовать запись `manifest.json`
- [x] Возвращать `storage_path`
- [x] Возвращать относительные пути сохраненных страниц

---

## Service

- [x] Создать `src/crawler/services.py`
- [x] Добавить `SiteMarkdownCrawlerService`
- [x] Реализовать FIFO queue для BFS
- [x] Реализовать `visited`
- [x] Реализовать `discovered_from`
- [x] Применять canonicalization до постановки URL в очередь
- [x] Исключать дубли URL
- [x] Исключать внешние URL при `same_domain_only=True`
- [x] Ограничивать обход через `max_pages`
- [x] Собирать `RunStats`
- [x] Собирать `RunManifest`
- [x] Возвращать `CrawlRunResult`

---

## CLI

- [x] Создать `scripts/crawl_site_to_markdown.py`
- [x] Добавить аргумент `--url`
- [x] Добавить аргумент `--max-pages`
- [x] Добавить аргумент `--output-dir`
- [x] Добавить аргумент `--delay`
- [x] Создавать `CrawlConfig` из CLI-аргументов
- [x] Вызывать `SiteMarkdownCrawlerService`
- [x] Печатать summary результата
- [x] Печатать путь к output

---

# Final Validation

- [x] `ruff check .`
- [x] `ruff check . --fix`
- [ ] Все Phase Verification Checklist закрыты.
- [ ] CLI успешно выполняет интеграционный прогон.
- [ ] Структура output соответствует Spec.
- [ ] `manifest.json` соответствует Spec.
- [ ] Markdown-файлы содержат YAML front matter.
- [ ] MVP соответствует всем Acceptance Criteria из Implementation Spec.

---

## Manual Run Command

Команда для ручного интеграционного прогона после реализации:

```powershell
python scripts\crawl_site_to_markdown.py --url https://example.com --max-pages 10 --delay 10-20 --output-dir output
```

По умолчанию crawler делает случайную паузу `2-5` секунд между запросами. Для override используйте `--delay 10-20` или фиксированное значение `--delay 3`.

Перед ручным прогоном требуется установить `crawl4ai` в активный `venv`, иначе CLI завершится ошибкой импорта.
