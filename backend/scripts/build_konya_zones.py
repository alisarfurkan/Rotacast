"""Build the Konya agro-microclimate zone files in data/zones/ (see rotacast.zones.build).

Usage: python backend/scripts/build_konya_zones.py [--preview PATH]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rotacast.zones.build import build, render_preview  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", help="write a PNG preview of the zones to this path")
    args = ap.parse_args()
    result = build()
    if args.preview:
        render_preview(result, args.preview)
        print("preview:", args.preview)


if __name__ == "__main__":
    main()
