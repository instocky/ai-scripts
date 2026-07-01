"""Wrapper для CLI viewer'а — добавляет src/ в sys.path.

Использование вместо `python -m tracing`, который требует PYTHONPATH=src:
    python scripts\view_traces.py --last 24h --limit 20
    python scripts\view_traces.py --by-span --service openlit_pipeline
    python scripts\view_traces.py --help
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tracing.cli import main  # noqa: E402

raise SystemExit(main())