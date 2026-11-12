"""Build the Konya Closed Basin scenario report and write data/demo/basin_report_konya.json."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from rotacast.regional import BasinParams, build_basin_report  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    t = time.time()
    rep = build_basin_report(BasinParams())
    out = ROOT / "data" / "demo" / "basin_report_konya.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, allow_nan=False, indent=1), encoding="utf-8")
    g = rep["grace"]
    print(f"built in {time.time() - t:.0f}s -> {out} ({out.stat().st_size / 1024:.0f} kB)")
    print(f"cells={rep['totals']['n_cells']} irrigated={rep['totals']['irrigated_ha'] / 1e3:.0f} kha "
          f"baseline demand p50={rep['baseline']['irrigation_demand_mm3_yr']['p50']:.0f} Mm3/yr")
    if g["available"]:
        print(f"GRACE {g['period'][0]}..{g['period'][1]}: {g['trend_cm_yr']:+.2f} cm/yr "
              f"(CI {g['trend_ci95_cm_yr'][0]:+.2f}..{g['trend_ci95_cm_yr'][1]:+.2f}) over {g['area_km2']:.0f} km2 "
              f"= {g['volume_change_mm3_yr']:+.0f} Mm3/yr")
    else:
        print("GRACE unavailable:", g["note"]["en"])
    print(f"{'archetype':16} {'adopt':>5} {'dWater p50 Mm3':>14} {'%GRACE':>7}  production change @10y (t/yr)")
    for arch, by_a in rep["scenarios"].items():
        for a, hz in by_a.items():
            h = hz["10"]
            off = h["grace_offset_pct"]["p50"] if h["grace_offset_pct"] else float("nan")
            prod = ", ".join(f"{x['crop_id']} {x['change_t_yr']:+,.0f}" for x in h["production_change_t_yr"][:4])
            print(f"{arch:16} {float(a):5.0%} {h['irrigation_change_mm3_yr']['p50']:14.1f} {off:7.1f}  {prod}")


if __name__ == "__main__":
    main()
