# Crawler Implementation Plan

## Цель

Разбить реализацию MVP crawler на небольшие фазы с понятным порядком работ, ожидаемым результатом и `Definition of Done` для каждой фазы.

Этот документ дополняет [crawler_implementation_spec_v1.md](C:\Projects\Python\0630_ai-scripts\docs\crawler_implementation_spec_v1.md) и отвечает на вопрос: в каком порядке писать код.

---

## Общие правила реализации

- реализовывать только MVP из spec;
- не добавлять новые абстракции без подтвержденной необходимости;
- не выходить за пределы `src/crawler` и связанного CLI, если это не требуется задачей;
- сохранять разделение `client -> services -> storage`;
- вместо запуска тестов подготовить конкретные команды для ручного прогона пользователем;
- после изменений обязательно прогонять:

```powershell
ruff check .
ruff check . --fix
```

---

## Phase 1 — Foundation

### Задачи

- создать пакет `src/crawler/`;
- добавить `__init__.py`;
- создать `models.py`;
- описать `CrawlConfig`, `CrawledPage`, `RunStats`, `RunManifest`, `CrawlRunResult`;
- создать `url_utils.py`;
- реализовать `normalize_url()`;
- реализовать проверку same-domain policy;
- реализовать преобразование URL в путь внутри `pages/`.

### Результат фазы

Есть базовые модели и чистые функции, на которые будет опираться вся остальная реализация.

### Definition of Done

- пакет `src/crawler/` создан;
- модели отражают spec и не содержат лишних полей;
- `normalize_url()` обрабатывает базовые кейсы:
  - trailing slash;
  - fragment removal;
  - `utm_*` query params;
  - `index.html`;
  - relative URL against base URL;
- функция формирования output path сохраняет структуру каталогов сайта;
- код проходит `ruff check .` и `ruff check . --fix`.

### Verification Checklist

- [ ] `normalize_url()` корректно удаляет fragment.
- [ ] `utm_*` удаляются.
- [ ] `index.html` схлопывается.
- [ ] Относительные URL корректно резолвятся.
- [ ] URL другого домена отбрасываются.
- [ ] Path generation повторяемый.
- [ ] `ruff check .`

---

## Phase 2 — Crawl Client

### Задачи

- создать `src/crawler/client.py`;
- реализовать `Crawl4AiClient`;
- определить формат результата, который возвращает клиент сервису;
- локализовать обработку ошибок crawl provider внутри client-слоя;
- подготовить извлечение:
  - итогового URL;
  - title;
  - markdown;
  - внутренних ссылок страницы, если библиотека это позволяет.

### Результат фазы

Интеграция с `crawl4ai` изолирована в одном модуле и не протекает в service layer.

### Definition of Done

- `crawl4ai` импортируется только из `src/crawler/client.py`;
- service не знает деталей `crawl4ai`;
- клиент умеет вернуть либо успешный page result, либо структурированную ошибку;
- клиент не пишет файлы и не занимается orchestration;
- код проходит `ruff check .` и `ruff check . --fix`.

### Verification Checklist

- [ ] Crawl4AI успешно обрабатывает одну страницу.
- [ ] Title извлекается.
- [ ] Markdown извлекается.
- [ ] Ссылки извлекаются.
- [ ] Ошибка страницы корректно сериализуется.
- [ ] Service ничего не знает о Crawl4AI.

---

## Phase 3 — Storage

### Задачи

- создать `src/crawler/storage.py`;
- реализовать `MarkdownStorage`;
- создать layout каталога прогона;
- реализовать запись `.md`;
- добавить YAML front matter;
- реализовать запись `manifest.json`;
- вернуть `storage_path` и относительные пути сохраненных файлов.

### Результат фазы

Storage полностью владеет output layout и умеет сохранять все артефакты прогона.

### Definition of Done

- создается структура:

```text
output/<domain>/<timestamp>/
  manifest.json
  pages/
```

- markdown-файлы сохраняются с зеркалированием структуры сайта;
- `manifest.json` записывается отдельным файлом;
- front matter добавляется в каждый markdown;
- service не собирает файловые пути вручную;
- код проходит `ruff check .` и `ruff check . --fix`.

### Verification Checklist

- [ ] Создается output/<domain>/<timestamp>.
- [ ] Создается pages/.
- [ ] Markdown записывается.
- [ ] YAML front matter присутствует.
- [ ] Manifest валиден.
- [ ] Relative paths корректны.

---

## Phase 4 — Service

### Задачи

- создать `src/crawler/services.py`;
- реализовать `SiteMarkdownCrawlerService`;
- собрать BFS-обход:
  - queue;
  - visited;
  - `discovered_from`;
- вызывать canonicalization до постановки URL в очередь;
- отбрасывать дубликаты и внешние URL;
- ограничивать обход через `max_pages`;
- собирать `RunManifest` и `RunStats`;
- возвращать `CrawlRunResult`.

### Результат фазы

Появляется основной orchestration layer, который связывает client, domain logic и storage.

### Definition of Done

- используется именно BFS;
- URL canonicalization применяется до deduplication;
- сохраняется статистика:
  - `discovered`;
  - `crawled`;
  - `saved`;
  - `failed`;
  - `skipped`;
- результатом работы сервиса является `CrawlRunResult`;
- service не знает layout `output/`;
- код проходит `ruff check .` и `ruff check . --fix`.

### Verification Checklist

- [ ] BFS действительно используется.
- [ ] URL не обходятся повторно.
- [ ] max_pages соблюдается.
- [ ] delay range применяется между запросами.
- [ ] discovered_from сохраняется.
- [ ] Stats считаются корректно.

---

## Phase 5 — CLI

### Задачи

- создать `scripts/crawl_site_to_markdown.py`;
- добавить чтение аргументов:
  - `--url`;
  - `--max-pages`;
  - `--output-dir`;
  - `--delay`;
- создать `CrawlConfig`;
- вызвать service;
- вывести короткий summary по результату прогона.

### Результат фазы

Появляется рабочая точка входа для ручного запуска MVP.

### Definition of Done

- CLI не содержит crawl-логики;
- CLI не работает с `crawl4ai` напрямую;
- CLI не собирает `manifest.json`;
- CLI использует только config + service result;
- выводит пользователю путь к результату и summary по stats;
- код проходит `ruff check .` и `ruff check . --fix`.

### Verification Checklist

- [ ] CLI запускается.
- [ ] --url читается.
- [ ] --max-pages читается.
- [ ] Summary печатается.
- [ ] Output path отображается.

---

## Phase 6 — Integration Pass

### Задачи

- выполнить ручной прогон на небольшом сайте;
- проверить структуру output;
- проверить корректность `manifest.json`;
- проверить YAML front matter;
- проверить отсутствие явных дублей URL;
- проверить ограничение `max_pages`.

### Результат фазы

Есть подтверждение, что vertical slice реально работает end-to-end на небольшом сайте.

### Definition of Done

- CLI запускается без ручных правок кода;
- создается директория результата;
- хотя бы несколько страниц сохраняются в markdown;
- `manifest.json` отражает реальное состояние прогона;
- статистика `stats` выглядит правдоподобно;
- подготовлена команда для ручного интеграционного прогона пользователем.

### Verification Checklist

- [ ] output соответствует spec.
- [ ] manifest соответствует spec.
- [ ] YAML присутствует.
- [ ] Markdown читаемый.
- [ ] Дубликатов нет.

---

## Suggested Execution Order

Рекомендуемый порядок разработки:

1. `models.py`
2. `url_utils.py`
3. `client.py`
4. `storage.py`
5. `services.py`
6. `scripts/crawl_site_to_markdown.py`
7. ручной интеграционный прогон

---

## Risks To Watch

- слишком агрессивная canonicalization может склеить разные страницы;
- слишком слабая canonicalization приведет к дублям;
- provider может возвращать неполные ссылки или нестабильный markdown;
- зеркалирование структуры сайта может привести к редким коллизиям путей;
- service может начать протекать в storage details, если не держать границу слоев.

---

## Ready For Coding

После подготовки этих фаз дальнейшее проектирование считается достаточным для MVP. Следующий шаг — переход к реализации по фазам без расширения scope.
