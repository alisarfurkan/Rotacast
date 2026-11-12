"""Build the Konya demo FieldReport and write data/demo/field_report_konya.json."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from rotacast.report import build_field_report  # noqa: E402

REQUEST = {
    "lat": 37.60, "lon": 32.75,
    "current_rotation": [{"crop_id": "wheat_winter", "irrigation": "none"},
                         {"crop_id": "sugar_beet", "irrigation": "full"},
                         {"crop_id": "maize_grain", "irrigation": "full"}],
    "constraints": {"water_access": "limited", "max_irrigated_share": 0.5},
    "priorities": {"water": 0.3, "soil": 0.25, "income": 0.25, "erosion": 0.1, "risk": 0.1},
    "scenario": {"delta_t_c": 0, "precip_change_pct": 0},
    "lang": "tr",
}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    t = time.time()
    rep = build_field_report(REQUEST)
    dt = time.time() - t
    out = ROOT / "data" / "demo" / "field_report_konya.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, allow_nan=False, indent=1), encoding="utf-8")
    print(f"built in {dt:.1f}s -> {out} ({out.stat().st_size / 1024:.0f} kB), {len(rep['facts'])} facts")
    print(f"{'archetype':16} {'rotation':58} {'score':>5} {'water m3/ha':>11} {'income $/ha':>11} {'N kg/ha':>8} {'eros':>5}")
    for s in rep["strategies"]:
        i = s["indicators"]
        print(f"{s['archetype']:16} {s['rotation_name']['en'][:58]:58} {s['score']:5.0f} {i['water_m3_ha_yr']['p50']:11.0f} "
              f"{i['income_usd_ha_yr']['p50']:11.0f} {i['n_balance_kg_ha_yr']:8.0f} {i['erosion_rel']:5.2f}")


if __name__ == "__main__":
    main()
