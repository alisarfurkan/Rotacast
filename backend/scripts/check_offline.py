"""Offline demo safety check: with ROTACAST_OFFLINE=1 the Konya field report must still be built from cached CHIRPS-corrected
rain, and the stored basin report should have corrected cells. Prints a PASS/FAIL table; exit code 1 on any failure."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ["ROTACAST_OFFLINE"] = "1"  # before importing rotacast so every connector sees it

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_demo_report import REQUEST  # noqa: E402
from rotacast.report import build_field_report  # noqa: E402

BASIN = ROOT / "data" / "demo" / "basin_report_konya.json"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    rows: list[tuple[str, bool, str]] = []

    rep, pc = None, None
    try:
        t = time.time()
        rep = build_field_report(REQUEST)
        rows.append(("field report built offline", True, f"{time.time() - t:.1f}s, {len(rep['strategies'])} strategies"))
        pc = rep.get("precip_correction")
    except Exception as exc:  # noqa: BLE001
        rows.append(("field report built offline", False, f"{type(exc).__name__}: {exc}"))

    if rep is not None:
        rows.append(("precip_correction present", pc is not None, "None -> fell back to raw POWER rain" if pc is None else "ok"))
        src = (pc or {}).get("source_id")
        rows.append(("precip source is chirps", src == "chirps", f"source_id={src}"))
        cov = (pc or {}).get("coverage")
        full = bool(cov) and not cov.get("missing_years") and cov.get("obtained_years") == cov.get("requested_years")
        rows.append(("coverage complete", full, f"{cov}" if cov else "no coverage info"))

    try:
        cells = json.loads(BASIN.read_text(encoding="utf-8"))["cells"]
        n = sum(1 for c in cells if (c.get("precip_correction") or {}).get("applied"))
        rows.append(("basin cells precip_correction.applied", n == len(cells) and n > 0, f"{n}/{len(cells)} cells"))
    except Exception as exc:  # noqa: BLE001
        rows.append(("basin cells precip_correction.applied", False, f"{type(exc).__name__}: {exc}"))

    w = max(len(r[0]) for r in rows)
    print(f"{'check':{w}}  result  detail")
    for name, ok, detail in rows:
        print(f"{name:{w}}  {'PASS' if ok else 'FAIL':6}  {detail}")
    ok_all = all(r[1] for r in rows)
    print("\nOVERALL:", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
