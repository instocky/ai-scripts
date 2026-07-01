"""Обход Windows-бага `openlit.init(pricing_json=...)`.

OpenLIT 1.42.x использует `urlparse(path).scheme` для определения URL-это
или путь. На Windows `urlparse("C:\\...").scheme == "c"` (драйв = scheme),
`requests.get("c:...")` молча падает → `pricing_info = {}` → cost = 0 для
всех кастомных моделей. `file:///C:/...` `requests` тоже не понимает без
`requests-file`.

Решение: читаем `pricing.json` сами и подменяем `openlit.fetch_pricing_info`
ДО вызова `openlit.init()`. Внутри `openlit/__init__.py` функция импортируется
через `from openlit.__helpers import fetch_pricing_info` — это локальный
binding в namespace `openlit`, который мы и перезаписываем.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_DEFAULT_PRICING = Path(__file__).resolve().parent.parent.parent / "pricing.json"


def install_openlit_pricing(pricing_json_path: Path | str | None = None) -> bool:
    """Подменить `openlit.fetch_pricing_info` нашей версией.

    Args:
        pricing_json_path: явный путь к JSON. Если None — берём env
            `OPENLIT_PRICING_JSON`, иначе дефолт `<repo>/pricing.json`.

    Returns:
        True если патч установлен; False если файл не найден — тогда
        OpenLIT останется на built-in pricing (cost=0 для date-suffix моделей).
    """
    if pricing_json_path is None:
        env = os.getenv("OPENLIT_PRICING_JSON")
        path = Path(env) if env else _DEFAULT_PRICING
    else:
        path = Path(pricing_json_path)

    if not path.exists():
        print(
            f"[tracing] pricing.json not found at {path}, "
            "using built-in defaults. cost for unknown models will be 0."
        )
        return False

    with open(path, encoding="utf-8") as f:
        custom = json.load(f)

    def _patched(pricing_json=None):  # noqa: ARG001
        # Аргумент openlit всё равно передаёт, но у нас уже загруженный dict.
        return custom

    import openlit
    openlit.fetch_pricing_info = _patched
    print(
        f"[tracing] custom pricing loaded from {path}: "
        f"{len(custom.get('chat', {}))} chat models"
    )
    return True