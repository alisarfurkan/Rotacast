"""Small planar/spherical helpers for a field polygon (GeoJSON order: [lon, lat], WGS84)."""
from __future__ import annotations

import math

EARTH_RADIUS_M = 6378137.0  # same sphere as @turf/area
HA_PER_M2 = 1e-4
_EPS = 1e-12


def open_ring(coords: list) -> list[tuple[float, float]]:
    """[lon, lat] points without the closing duplicate; consecutive duplicate points are dropped."""
    pts = [(float(p[0]), float(p[1])) for p in coords]
    out: list[tuple[float, float]] = []
    for p in pts:
        if not out or p != out[-1]:
            out.append(p)
    if len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


def closed_ring(coords: list) -> list[list[float]]:
    pts = open_ring(coords)
    return [[x, y] for x, y in pts] + [[pts[0][0], pts[0][1]]] if pts else []


def _orient(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a, b, p) -> bool:
    return (min(a[0], b[0]) - _EPS <= p[0] <= max(a[0], b[0]) + _EPS
            and min(a[1], b[1]) - _EPS <= p[1] <= max(a[1], b[1]) + _EPS)


def segments_intersect(p1, p2, p3, p4) -> bool:
    """True if closed segments p1p2 and p3p4 share at least one point."""
    d1, d2 = _orient(p3, p4, p1), _orient(p3, p4, p2)
    d3, d4 = _orient(p1, p2, p3), _orient(p1, p2, p4)
    if ((d1 > _EPS and d2 < -_EPS) or (d1 < -_EPS and d2 > _EPS)) and \
       ((d3 > _EPS and d4 < -_EPS) or (d3 < -_EPS and d4 > _EPS)):
        return True
    if abs(d1) <= _EPS and _on_segment(p3, p4, p1):
        return True
    if abs(d2) <= _EPS and _on_segment(p3, p4, p2):
        return True
    if abs(d3) <= _EPS and _on_segment(p1, p2, p3):
        return True
    if abs(d4) <= _EPS and _on_segment(p1, p2, p4):
        return True
    return False


def is_self_intersecting(pts: list[tuple[float, float]]) -> bool:
    """Open ring (no closing duplicate). Non-adjacent edges must not touch; adjacent edges may only share their vertex."""
    n = len(pts)
    edges = [(pts[i], pts[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            adjacent = j == i + 1 or (i == 0 and j == n - 1)
            a, b = edges[i]
            c, d = edges[j]
            if adjacent:
                # collinear overlap (a spike folding back on itself) also counts as a self-intersection
                shared = b if j == i + 1 else a
                other_i = a if shared is b else b
                other_j = d if shared is c else c
                if abs(_orient(shared, other_i, other_j)) <= _EPS and \
                   ((other_i[0] - shared[0]) * (other_j[0] - shared[0]) + (other_i[1] - shared[1]) * (other_j[1] - shared[1])) > 0:
                    return True
                continue
            if segments_intersect(a, b, c, d):
                return True
    return False


def area_ha(pts: list[tuple[float, float]]) -> float:
    """Geodesic-on-sphere polygon area in hectares (the @turf/area / Chamberlain-Duquette formula, R = 6378137 m)."""
    n = len(pts)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        lo1, la1 = pts[i]
        lo2, la2 = pts[(i + 1) % n]
        total += math.radians(lo2 - lo1) * (2.0 + math.sin(math.radians(la1)) + math.sin(math.radians(la2)))
    return abs(total) * EARTH_RADIUS_M ** 2 / 2.0 * HA_PER_M2


def centroid(pts: list[tuple[float, float]]) -> tuple[float, float]:
    """Area-weighted planar centroid in lon/lat (fine at field scale); falls back to the vertex mean if degenerate."""
    n = len(pts)
    ox, oy = pts[0]  # work relative to the first vertex: keeps precision for lon/lat of a small field
    a = cx = cy = 0.0
    for i in range(n):
        x1, y1 = pts[i][0] - ox, pts[i][1] - oy
        x2, y2 = pts[(i + 1) % n][0] - ox, pts[(i + 1) % n][1] - oy
        cr = x1 * y2 - x2 * y1
        a += cr
        cx += (x1 + x2) * cr
        cy += (y1 + y2) * cr
    if abs(a) < 1e-18:
        return sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    return ox + cx / (3.0 * a), oy + cy / (3.0 * a)
