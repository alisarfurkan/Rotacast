"""Konya agro-microclimate zones: built once by ``scripts/build_konya_zones.py``, looked up at runtime (lookup.py)."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ZONES_DIR = REPO_ROOT / "data" / "zones"
RAW_CACHE = "_raw"  # large raw downloads live in data/cache/_raw/<source> (gitignored)
