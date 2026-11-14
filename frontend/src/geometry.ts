// Small pure geometry helpers for the field-boundary editor (no dependencies).

export interface LL { lat: number; lon: number }

const R = 6378137 // metres, same radius as @turf/area
const rad = (d: number) => (d * Math.PI) / 180

/** Spherical polygon area in m² (the formula @turf/area uses: Chamberlain & Duquette, R = 6378137). */
export function areaM2(ring: LL[]): number {
  const n = ring.length
  if (n < 3) return 0
  let total = 0
  for (let i = 0; i < n; i++) {
    const p1 = ring[i], p2 = ring[(i + 1) % n], p3 = ring[(i + 2) % n]
    total += (rad(p3.lon) - rad(p1.lon)) * Math.sin(rad(p2.lat))
  }
  return Math.abs((total * R * R) / 2)
}
export const areaHa = (ring: LL[]) => areaM2(ring) / 10000

/** Area-weighted centroid (planar, on lon/lat shifted to the first vertex); falls back to the vertex mean. */
export function centroid(ring: LL[]): LL {
  const n = ring.length
  const lat0 = ring[0].lat, lon0 = ring[0].lon
  const k = Math.cos(rad(lat0))
  const pts = ring.map((p) => ({ x: (p.lon - lon0) * k, y: p.lat - lat0 }))
  let a = 0, cx = 0, cy = 0
  for (let i = 0; i < n; i++) {
    const p = pts[i], q = pts[(i + 1) % n]
    const f = p.x * q.y - q.x * p.y
    a += f; cx += (p.x + q.x) * f; cy += (p.y + q.y) * f
  }
  if (Math.abs(a) < 1e-18) {
    return { lat: ring.reduce((s, p) => s + p.lat, 0) / n, lon: ring.reduce((s, p) => s + p.lon, 0) / n }
  }
  return { lat: lat0 + cy / (3 * a), lon: lon0 + cx / (3 * a) / k }
}

const cross = (o: LL, a: LL, b: LL) => (a.lon - o.lon) * (b.lat - o.lat) - (a.lat - o.lat) * (b.lon - o.lon)
const onSeg = (a: LL, b: LL, p: LL) =>
  Math.min(a.lon, b.lon) <= p.lon && p.lon <= Math.max(a.lon, b.lon) && Math.min(a.lat, b.lat) <= p.lat && p.lat <= Math.max(a.lat, b.lat)

function segmentsIntersect(a: LL, b: LL, c: LL, d: LL): boolean {
  const d1 = cross(a, b, c), d2 = cross(a, b, d), d3 = cross(c, d, a), d4 = cross(c, d, b)
  if (((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))) return true
  if (d1 === 0 && onSeg(a, b, c)) return true
  if (d2 === 0 && onSeg(a, b, d)) return true
  if (d3 === 0 && onSeg(c, d, a)) return true
  if (d4 === 0 && onSeg(c, d, b)) return true
  return false
}

/** True if any two non-adjacent edges of the (implicitly closed) ring cross or touch. */
export function selfIntersects(ring: LL[]): boolean {
  const n = ring.length
  if (n < 4) return false
  for (let i = 0; i < n; i++) {
    const a = ring[i], b = ring[(i + 1) % n]
    for (let j = i + 1; j < n; j++) {
      if (j === i + 1 || (i === 0 && j === n - 1)) continue // adjacent edges share a vertex
      if (segmentsIntersect(a, b, ring[j], ring[(j + 1) % n])) return true
    }
  }
  return false
}

export const midpoint = (a: LL, b: LL): LL => ({ lat: (a.lat + b.lat) / 2, lon: (a.lon + b.lon) / 2 })

/** GeoJSON Polygon with a closed ring, [lon, lat]. */
export function toGeoJSON(ring: LL[]) {
  const c = ring.map((p) => [+p.lon.toFixed(6), +p.lat.toFixed(6)])
  c.push([...c[0]])
  return { type: 'Polygon' as const, coordinates: [c] }
}

export const MIN_HA = 0.01
export const MAX_HA = 10000
