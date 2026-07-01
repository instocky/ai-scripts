"""Smoke-тест: запускаем simple_pipeline через subprocess → проверяем traces.db."""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# venv проекта — pytest может быть запущен из глобального python, но
# openlit/opentelemetry стоят в venv. Subprocess должен идти в venv,
# иначе упадёт на `import opentelemetry`.
_VENV_PYTHON = REPO_ROOT / "venv" / "Scripts" / "python.exe"


def _run_pipeline(script: str, *, db_path: Path) -> None:
    """Запустить скрипт в subprocess; db_path передаётся через env.

    Используем venv-python напрямую (а не sys.executable) — pytest может
    крутиться в глобальном python, а openlit/opentelemetry лежат в venv.

    Env наследуем целиком от pytest-процесса (PATH / SYSTEMROOT / TEMP /
    USERPROFILE нужны для загрузки Windows-DLL типа `_overlapped` —
    asyncio-импорт openlit'а без них падает с WinError 10106). Убираем
    только PYTHONPATH/PYTHONHOME — pytest иногда инжектит site-packages
    глобального python, что ломает venv-isolation.
    """
    python_exe = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["TRACING_DB_PATH"] = str(db_path)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)

    result = subprocess.run(
        [python_exe, str(REPO_ROOT / "scripts" / script)],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)


def test_simple_pipeline_writes_trace(tmp_path: Path) -> None:
    db = tmp_path / "traces.db"

    _run_pipeline("simple_pipeline.py", db_path=db)

    assert db.exists(), f"traces.db not created at {db}"
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT service, status FROM traces ORDER BY started_at DESC"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) >= 1
    assert rows[0][0] == "simple_pipeline"
    # OK — happy path; UNSET — если run не дошёл до явного set_status;
    # ERROR — если пайплайн упал. Всё валидно: smoke пишет трейс в любом случае.
    assert rows[0][1] in {"OK", "ERROR", "UNSET"}