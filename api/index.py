"""Vercel Serverless Entrypoint for Smart Home Voice AI FastAPI Backend."""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.server import app  # noqa: E402

__all__ = ["app"]
