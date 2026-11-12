"""Elevation and slope from AWS Open Data terrain tiles (terrarium PNG, SRTM-derived).

source_id ``srtm_terrain_tiles``. https://registry.opendata.aws/terrain-tiles/
Elevation (m) = R*256 + G + B/256 - 32768.
"""
from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image

from .cache import cached_get_bytes

SOURCE_ID = "srtm_terrain_tiles"
URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
ZOOM = 12  # ~30-38 m/px at mid-latitudes (comparable to native SRTM 1 arc-second)
TILE = 256


def decode_terrarium(png: bytes) -> np.ndarray:
    """Decode a terrarium PNG into a 256x256 float array of elevation in metres."""
    rgb = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), dtype=np.float64)
    return rgb[..., 0] * 256.0 + rgb[..., 1] + rgb[..., 2] / 256.0 - 32768.0


def _global_pixel(lat: float, lon: float, z: int) -> tuple[float, float]:
    """Web-mercator global pixel coordinates (x, y) of a point at zoom z."""
    n = 2 ** z * TILE
    px = (lon + 180.0) / 360.0 * n
    s = math.sin(math.radians(lat))
    py = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return px, py


def slope_from_window(win: np.ndarray, cell_m: float) -> float:
    """Slope (%) at the centre of a 3x3 elevation window (Horn's method), cell size in metres."""
    a, b, c = win[0]
    d, _, f = win[1]
    g, h, i = win[2]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * cell_m)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * cell_m)
    return float(math.hypot(dzdx, dzdy) * 100.0)


def fetch_terrain(lat: float, lon: float) -> dict:
    """Return {"elevation_m", "slope_pct", "source_id"} at a point (slope: Horn 3x3 at z12)."""
    z = ZOOM
    px, py = _global_pixel(lat, lon, z)
    gx, gy = int(px), int(py)
    win = np.zeros((3, 3))
    tiles: dict[tuple[int, int], np.ndarray] = {}
    for j in range(3):
        for k in range(3):
            x, y = gx + k - 1, gy + j - 1
            key = (x // TILE, y // TILE)
            if key not in tiles:
                png = cached_get_bytes(SOURCE_ID, URL.format(z=z, x=key[0], y=key[1]))
                tiles[key] = decode_terrarium(png)
            win[j, k] = tiles[key][y % TILE, x % TILE]
    cell_m = 40075016.686 * math.cos(math.radians(lat)) / (2 ** z * TILE)
    return {"elevation_m": float(win[1, 1]), "slope_pct": slope_from_window(win, cell_m),
            "source_id": SOURCE_ID}
