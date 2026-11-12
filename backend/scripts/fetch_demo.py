"""Fetch and cache all connector data for the demo (Konya) and sanity (Kansas) points.

Run from ``backend/``:  python scripts/fetch_demo.py
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rotacast.connectors.grace import KONYA_BBOX, fetch_tws  # noqa: E402
from rotacast.connectors.modis import fetch_landcover, fetch_ndvi  # noqa: E402
from rotacast.connectors.power import fetch_daily  # noqa: E402
from rotacast.connectors.soil import fetch_soil  # noqa: E402
from rotacast.connectors.terrain import fetch_terrain  # noqa: E402

POINTS = {"konya_demo": (37.60, 32.75), "kansas_sanity": (38.50, -98.50)}


def main() -> None:
    end = date.today() - timedelta(days=3)
    for name, (lat, lon) in POINTS.items():
        print(f"== {name} ({lat}, {lon})")
        # POWER lags real time by a few days; back off until the tail is non-empty
        while True:
            try:
                p = fetch_daily(lat, lon, date(1991, 1, 1), end)
                if p["tmax"].notna().iloc[-1] or end < date.today() - timedelta(days=30):
                    break
            except Exception as exc:  # noqa: BLE001
                print("  POWER error:", exc)
                raise
            end -= timedelta(days=1)
        last_valid = p.dropna(how="all").index.max()
        print(f"  POWER: {len(p)} rows {p.index.min().date()}..{p.index.max().date()} "
              f"(last valid {last_valid.date()}), elev {p.attrs['elevation_m']} m, "
              f"missing% {(p.isna().mean() * 100).round(2).to_dict()}")
        n = fetch_ndvi(lat, lon, date(2000, 2, 1), date.today())
        print(f"  NDVI: {len(n)} rows {n.index.min().date()}..{n.index.max().date()}, "
              f"ndvi missing {n['ndvi'].isna().mean() * 100:.1f}%, reliability>1: "
              f"{(n['reliability'] > 1).mean() * 100:.1f}%")
        lc1 = fetch_landcover(lat, lon, 2001)
        lc2 = fetch_landcover(lat, lon, date.today().year)
        print(f"  Land cover (IGBP): 2001={lc1}, latest={lc2}  (12=cropland, 14=mosaic)")
        s = fetch_soil(lat, lon)
        print(f"  Soil[{s.source_id}]: {s.texture_class}, clay {s.clay_pct:.1f} sand {s.sand_pct:.1f} "
              f"silt {s.silt_pct:.1f}, SOC {s.soc_gkg:.1f} g/kg, pH {s.ph:.2f}, BD {s.bulk_density:.2f}, "
              f"fc {s.fc:.3f} wp {s.wp:.3f} TAW {s.taw_mm_per_m:.0f} mm/m")
        t = fetch_terrain(lat, lon)
        print(f"  Terrain: elev {t['elevation_m']:.1f} m, slope {t['slope_pct']:.2f}% ({t['source_id']})")
    g = fetch_tws(KONYA_BBOX)
    print(f"== GRACE Konya bbox {KONYA_BBOX}: {len(g)} months {g.index.min().date()}..{g.index.max().date()}")
    yrs = (g.index - g.index[0]).days / 365.25
    import numpy as np
    slope = np.polyfit(yrs, g.values, 1)[0]
    print(f"  linear trend {slope:.2f} cm/yr (all), {np.polyfit(yrs[yrs > 8], g.values[yrs > 8], 1)[0]:.2f} cm/yr (2010+)")


if __name__ == "__main__":
    main()
