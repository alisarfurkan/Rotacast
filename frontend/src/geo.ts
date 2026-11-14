import type { Geom } from './types'

type Ring = number[][]

function inRing(x: number, y: number, ring: Ring): boolean {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]
    const [xj, yj] = ring[j]
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

function inPolygon(x: number, y: number, rings: Ring[]): boolean {
  if (!rings.length || !inRing(x, y, rings[0])) return false
  for (let k = 1; k < rings.length; k++) if (inRing(x, y, rings[k])) return false
  return true
}

/** Ray-casting point-in-polygon for GeoJSON Polygon / MultiPolygon (lon, lat order). */
export function inGeometry(lon: number, lat: number, g: Geom): boolean {
  return g.type === 'Polygon'
    ? inPolygon(lon, lat, g.coordinates)
    : g.coordinates.some((poly) => inPolygon(lon, lat, poly))
}
