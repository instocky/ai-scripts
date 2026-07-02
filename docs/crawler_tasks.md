# Crawler Tasks

Чеклист атомарных задач для реализации MVP crawler. Документ предназначен для пошагового закрытия работ по мере написания кода.

Связанные документы:

- [crawler_implementation_spec_v1.md](C:\Projects\Python\0630_ai-scripts\docs\crawler_implementation_spec_v1.md)
- [crawler_implementation_plan.md](C:\Projects\Python\0630_ai-scripts\docs\crawler_implementation_plan.md)

---

## Foundation

- [ ] Создать пакет `src/crawler/`
- [ ] Добавить `src/crawler/__init__.py`
- [ ] Создать `src/crawler/models.py`
- [ ] Добавить `CrawlConfig`
- [ ] Добавить `CrawledPage`
- [ ] Добавить `RunStats`
- [ ] Добавить `RunManifest`
- [ ] Добавить `CrawlRunResult`
- [ ] Создать `src/crawler/url_utils.py`
- [ ] Реализовать `normalize_url()`
- [ ] Реализовать same-domain filtering
- [ ] Реализовать преобразование URL в путь внутри `pages/`

---

## Crawl Client

- [ ] Создать `src/crawler/client.py`
- [ ] Добавить `Crawl4AiClient`
- [ ] Изолировать импорт `crawl4ai` внутри `client.py`
- [ ] Реализовать crawl одной страницы
- [ ] Извлекать `title`
- [ ] Извлекать `markdown`
- [ ] Извлекать ссылки для дальнейшего обхода
- [ ] Добавить структурированную обработку ошибок client-слоя

---

## Storage

- [ ] Создать `src/crawler/storage.py`
- [ ] Добавить `MarkdownStorage`
- [ ] Реализовать создание каталога прогона
- [ ] Реализовать структуру `output/<domain>/<timestamp>/pages/`
- [ ] Реализовать запись markdown-файлов
- [ ] Добавить YAML front matter
- [ ] Реализовать запись `manifest.json`
- [ ] Возвращать `storage_path`
- [ ] Возвращать относительные пути сохраненных страниц

---

## Service

- [ ] Создать `src/crawler/services.py`
- [ ] Добавить `SiteMarkdownCrawlerService`
- [ ] Реализовать FIFO queue для BFS
- [ ] Реализовать `visited`
- [ ] Реализовать `discovered_from`
- [ ] Применять canonicalization до постановки URL в очередь
- [ ] Исключать дубли URL
- [ ] Исключать внешние URL при `same_domain_only=True`
- [ ] Ограничивать обход через `max_pages`
- [ ] Собирать `RunStats`
- [ ] Собирать `RunManifest`
- [ ] Возвращать `CrawlRunResult`

---

## CLI

- [ ] Создать `scripts/crawl_site_to_markdown.py`
- [ ] Добавить аргумент `--url`
- [ ] Добавить аргумент `--max-pages`
- [ ] Добавить аргумент `--output-dir`
- [ ] Создавать `CrawlConfig` из CLI-аргументов
- [ ] Вызывать `SiteMarkdownCrawlerService`
- [ ] Печатать summary результата
- [ ] Печатать путь к output

---

# Final Validation

- [ ] `ruff check .`
- [ ] `ruff check . --fix`
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
python scripts\crawl_site_to_markdown.py --url https://example.com --max-pages 10 --output-dir output
```


```
