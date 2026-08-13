from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
DATA = ROOT / "data"
OUT = ROOT / "out"

MODE = os.getenv("TPRM_LENS_MODE", "replay").strip().lower() or "replay"
MODEL = os.getenv("TPRM_LENS_MODEL", "claude-sonnet-5")

if MODE not in {"replay", "live", "record"}:
    raise RuntimeError("TPRM_LENS_MODE must be replay, live, or record")

if MODE in {"live", "record"} and not os.getenv("ANTHROPIC_API_KEY"):
    raise RuntimeError(f"TPRM_LENS_MODE={MODE} requires ANTHROPIC_API_KEY")
