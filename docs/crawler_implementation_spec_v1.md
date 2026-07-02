# Crawler Implementation Spec v1

## Цель

Реализовать MVP-инструмент для обхода конкретного сайта и сохранения страниц в Markdown с полным `manifest.json` по результатам прогона.

Целевой vertical slice:

```text
website
  -> crawl
  -> markdown
  -> manifest
```

MVP не должен превращаться в универсальную crawler-platform. Задача текущего этапа: получить рабочий и расширяемый, но компактный контур.

---

## Scope MVP

Поддерживается один сценарий:

- вход: `base_url` конкретного сайта;
- обход страниц того же домена;
- стратегия обхода: `BFS`;
- сохранение каждой успешно обработанной страницы в `.md`;
- сохранение итогового `manifest.json`;
- ограничение по `max_pages`;
- запуск через CLI-скрипт.

В MVP не входят:

- публичный API;
- параллельный crawl;
- несколько crawl provider;
- сложная retry/politeness policy;
- отдельная БД;
- generalized plugin/framework abstraction.

---

## Архитектура

Структура в `src/`:

```text
src/
  crawler/
    __init__.py
    models.py
    services.py
    client.py
    storage.py
    url_utils.py
```

CLI:

```text
scripts/
  crawl_site_to_markdown.py
```

Распределение ответственности:

- `scripts/crawl_site_to_markdown.py`
  - парсит аргументы CLI;
  - создает `CrawlConfig`;
  - вызывает service;
  - печатает краткий summary.

- `src/crawler/services.py`
  - orchestration всего процесса;
  - BFS-обход;
  - canonicalization URL до постановки в очередь;
  - фильтрация URL;
  - вызов crawl-клиента;
  - сбор `RunManifest`;
  - возврат `CrawlRunResult`.

- `src/crawler/client.py`
  - локализует интеграцию с `crawl4ai`;
  - содержит `Crawl4AiClient`;
  - предоставляет простой метод для получения результата по одной странице.

- `src/crawler/storage.py`
  - полностью владеет структурой output;
  - создает директорию прогона;
  - сохраняет markdown-файлы;
  - пишет `manifest.json`;
  - возвращает пути артефактов.

- `src/crawler/url_utils.py`
  - canonicalization URL;
  - проверка домена;
  - преобразование URL в путь файла внутри `pages/`.

---

## Предметные модели

В `src/crawler/models.py`:

- `CrawlConfig`
  - `base_url: str`
  - `max_pages: int`
  - `output_dir: Path`
  - `same_domain_only: bool = True`
  - `delay_range_seconds: tuple[float, float] = (2.0, 5.0)`

- `CrawledPage`
  - `url: str`
  - `normalized_url: str`
  - `discovered_from: str | None`
  - `title: str | None`
  - `markdown: str`
  - `status: str`
  - `error: str | None`
  - `crawled_at: str`

- `RunStats`
  - `discovered: int`
  - `crawled: int`
  - `saved: int`
  - `failed: int`
  - `skipped: int`

- `RunManifest`
  - `version: int`
  - `started_at: str`
  - `finished_at: str`
  - `duration_ms: int`
  - `base_url: str`
  - `crawler: str`
  - `crawler_version: str | None`
  - `storage_dir: str`
  - `stats: RunStats`
  - `pages: list[dict]`

- `CrawlRunResult`
  - `manifest: RunManifest`
  - `storage_path: Path`
  - `duration_ms: int`

`RunManifest` является источником истины по результатам прогона. YAML front matter в markdown-файлах считается производным представлением.

---

## CrawlConfig

На первом этапе конфиг остается компактным.

Обязательные поля:

- `base_url`
- `max_pages`
- `output_dir`

Допустимый минимум дополнительных флагов:

- `same_domain_only`
- `delay_range_seconds` (default `2-5` seconds between requests)

Пока не добавляем без подтвержденной необходимости:

- `concurrency`
- `respect_robots`
- `exclude_patterns`
- `follow_redirects`
- `include_external`

Принцип: не тащить в MVP конфигурационные опции, которые не нужны для первого рабочего прогона.

---

## URL Canonicalization

Canonicalization выполняется до помещения URL в очередь.

Базовые правила:

- удалять `#fragment`;
- приводить `scheme` и `host` к нормализованному виду;
- считать `https://site.com` и `https://site.com/` одним URL;
- удалять tracking query params, например `utm_*`;
- query string не сохранять, если не доказана его ценность для конкретного сайта;
- политику для `index.html` зафиксировать явно: в MVP схлопывать `.../index.html` к родительскому пути;
- URL другого домена не ставить в очередь при `same_domain_only=True`.

Нужна отдельная функция:

```python
normalize_url(base_url: str, candidate_url: str) -> str | None
```

Если URL невалиден или не должен участвовать в обходе, функция возвращает `None`.

---

## Стратегия обхода

Используется `BFS`.

Причина выбора:

- обеспечивает предсказуемый порядок обхода;
- быстрее покрывает верхние уровни сайта;
- для небольшого MVP дает более ожидаемый результат, чем `DFS`.

Service должен хранить:

- `visited` для уже обработанных нормализованных URL;
- FIFO-очередь URL для `BFS`;
- связь `discovered_from`, чтобы отражать источник обнаружения страницы в manifest;
- random delay между запросами (default `2-5` seconds, override через CLI `--delay`).

---

## Интеграция с Crawl4AI

В `src/crawler/client.py` создается `Crawl4AiClient`.

Задача клиента:

- принять URL;
- выполнить crawl страницы через `crawl4ai`;
- вернуть нормализованный доменный результат для service.

На этом этапе не вводится общий интерфейс provider-level abstraction. Причина: в проекте пока один реальный провайдер, а преждевременный интерфейс не дает практической пользы для MVP.

Если позже появится второй провайдер, точка замены уже локализована в одном модуле.

---

## Storage

`MarkdownStorage` полностью владеет структурой output.

Целевая структура:

```text
output/
  example.com/
    20260702_183015/
      manifest.json
      pages/
        index.md
        about.md
        docs/
          install.md
          api.md
        blog/
          post-1.md
```

Принципы:

- не смешивать `manifest.json` и markdown-файлы в одном уровне;
- стараться сохранять структуру каталогов, близкую к структуре сайта;
- не использовать плоскую схему имен, если можно обойтись зеркалированием путей;
- добавлять hash только при реальной коллизии имен.

Service не должен вручную собирать пути внутри `output/`.

Storage должен:

1. создать директорию запуска;
2. создать `pages/`;
3. сохранить markdown;
4. сохранить `manifest.json`;
5. вернуть `storage_path`.

---

## Формат Markdown

Каждый markdown-файл содержит YAML front matter:

```yaml
---
url: https://example.com/docs/install
title: Install
status: success
crawled_at: 2026-07-02T18:30:15Z
---
```

Далее идет markdown-контент страницы.

Важно:

- `title` и метаданные обязательно должны быть в `manifest.json`;
- front matter нужен как удобное производное представление для индексации, поиска и LLM-задач;
- источником истины остается `manifest.json`.

---

## Manifest v1

`manifest.json` является главным артефактом прогона.

Пример структуры:

```json
{
  "version": 1,
  "started_at": "2026-07-02T18:30:15Z",
  "finished_at": "2026-07-02T18:31:02Z",
  "duration_ms": 47000,
  "base_url": "https://example.com",
  "crawler": "crawl4ai",
  "crawler_version": "x.y.z",
  "storage_dir": "output/example.com/20260702_183015",
  "stats": {
    "discovered": 84,
    "crawled": 42,
    "saved": 40,
    "failed": 2,
    "skipped": 42
  },
  "pages": [
    {
      "url": "https://example.com/docs/install",
      "normalized_url": "https://example.com/docs/install/",
      "title": "Install",
      "status": "success",
      "markdown_path": "pages/docs/install.md",
      "error": null,
      "discovered_from": "https://example.com/docs/"
    }
  ]
}
```

Назначение `stats`:

- быстро объяснять, почему реально сохранено меньше страниц, чем найдено;
- отделять найденные URL от реально обработанных;
- упрощать диагностику фильтров и ошибок.

---

## Tracing

Tracing добавляется только coarse-grained, если нужен сразу.

Рекомендуемые span'ы:

```text
crawl_run
  discover
  crawl_pages
  write_output
```

Почему не делаем span на каждую страницу в MVP:

- это создает шум на сайтах с большим числом страниц;
- ухудшает читаемость trace;
- может дать лишний overhead без большой пользы на первом этапе.

---

## Порядок реализации

1. Создать `src/crawler/models.py`.
2. Реализовать `src/crawler/url_utils.py`.
3. Реализовать `src/crawler/client.py` с `Crawl4AiClient`.
4. Реализовать `src/crawler/storage.py`.
5. Реализовать `src/crawler/services.py`.
6. Добавить `scripts/crawl_site_to_markdown.py`.
7. Проверить код:

```powershell
ruff check .
ruff check . --fix
```

8. Выполнить ручной интеграционный прогон на небольшом сайте.

Пример команды для пользователя:

```powershell
python scripts\crawl_site_to_markdown.py --url https://example.com --max-pages 10 --delay 10-20 --output-dir output
```

---

## Критерии готовности MVP

MVP считается готовым, если:

- можно указать URL сайта и получить каталог результата в `output/`;
- создается `manifest.json` с заполненным `stats`;
- успешно обработанные страницы сохраняются в `.md`;
- markdown-файлы содержат YAML front matter;
- обход ограничен одним доменом;
- дубли URL режутся canonicalization-логикой;
- порядок обхода воспроизводим и основан на `BFS`;
- CLI получает только `CrawlRunResult` и печатает summary, не зная внутреннего устройства storage.
