/**
 * Camera Zone Polygon Calibration Service & Geometry Utilities
 * Milestone M2.2B.7E: Handles normalized coordinate math, polygon validation,
 * geometric area & self-intersection detection, color palettes, and role permissions.
 */

export const ZONE_PALETTE = [
  {
    name: 'Emerald',
    stroke: '#10b981',
    fill: 'rgba(16, 185, 129, 0.22)',
    fillActive: 'rgba(16, 185, 129, 0.42)',
    text: 'text-emerald-400',
    border: 'border-emerald-500',
    bg: 'bg-emerald-950/70',
    badge: 'bg-emerald-950 border-emerald-800 text-emerald-300'
  },
  {
    name: 'Amber',
    stroke: '#f59e0b',
    fill: 'rgba(245, 158, 11, 0.22)',
    fillActive: 'rgba(245, 158, 11, 0.42)',
    text: 'text-amber-400',
    border: 'border-amber-500',
    bg: 'bg-amber-950/70',
    badge: 'bg-amber-950 border-amber-800 text-amber-300'
  },
  {
    name: 'Sky',
    stroke: '#0ea5e9',
    fill: 'rgba(14, 165, 233, 0.22)',
    fillActive: 'rgba(14, 165, 233, 0.42)',
    text: 'text-sky-400',
    border: 'border-sky-500',
    bg: 'bg-sky-950/70',
    badge: 'bg-sky-950 border-sky-800 text-sky-300'
  },
  {
    name: 'Purple',
    stroke: '#a855f7',
    fill: 'rgba(168, 85, 247, 0.22)',
    fillActive: 'rgba(168, 85, 247, 0.42)',
    text: 'text-purple-400',
    border: 'border-purple-500',
    bg: 'bg-purple-950/70',
    badge: 'bg-purple-950 border-purple-800 text-purple-300'
  },
  {
    name: 'Rose',
    stroke: '#f43f5e',
    fill: 'rgba(244, 63, 94, 0.22)',
    fillActive: 'rgba(244, 63, 94, 0.42)',
    text: 'text-rose-400',
    border: 'border-rose-500',
    bg: 'bg-rose-950/70',
    badge: 'bg-rose-950 border-rose-800 text-rose-300'
  },
  {
    name: 'Teal',
    stroke: '#14b8a6',
    fill: 'rgba(20, 184, 166, 0.22)',
    fillActive: 'rgba(20, 184, 166, 0.42)',
    text: 'text-teal-400',
    border: 'border-teal-500',
    bg: 'bg-teal-950/70',
    badge: 'bg-teal-950 border-teal-800 text-teal-300'
  }
];

export function getZoneColor(index) {
  return ZONE_PALETTE[Math.abs(index) % ZONE_PALETTE.length];
}

/**
 * Converts screen/pointer coordinates into normalized [0, 1] coordinates
 * based on the container/image bounding rectangle.
 */
export function toNormalizedCoord(pointerPos, containerRect) {
  if (!containerRect || containerRect.width <= 0 || containerRect.height <= 0) {
    return { x: 0, y: 0 };
  }
  const clientX = pointerPos.clientX ?? (pointerPos.touches && pointerPos.touches[0]?.clientX) ?? 0;
  const clientY = pointerPos.clientY ?? (pointerPos.touches && pointerPos.touches[0]?.clientY) ?? 0;

  const rawX = (clientX - containerRect.left) / containerRect.width;
  const rawY = (clientY - containerRect.top) / containerRect.height;

  const x = Math.max(0, Math.min(1, Number(rawX.toFixed(5))));
  const y = Math.max(0, Math.min(1, Number(rawY.toFixed(5))));

  return { x, y };
}

/**
 * Converts normalized [0, 1] coordinates into pixel coordinates
 * for SVG rendering or DOM positioning.
 */
export function toScreenCoord(normCoord, containerRect) {
  if (!containerRect) return { px: 0, py: 0 };
  const x = typeof normCoord?.x === 'number' ? normCoord.x : 0;
  const y = typeof normCoord?.y === 'number' ? normCoord.y : 0;
  return {
    px: Math.round(x * containerRect.width),
    py: Math.round(y * containerRect.height)
  };
}

/**
 * Converts a list of normalized {x, y} vertices into an SVG points string.
 * Uses 0-1000 coordinate space for high-precision SVG scaling.
 */
export function formatSvgPoints(polygon, scale = 1000) {
  if (!Array.isArray(polygon)) return '';
  return polygon
    .map((pt) => `${(pt.x * scale).toFixed(2)},${(pt.y * scale).toFixed(2)}`)
    .join(' ');
}

/**
 * Computes polygon centroid using normalized coordinates for placing zone labels.
 */
export function computePolygonCentroid(polygon) {
  if (!Array.isArray(polygon) || polygon.length === 0) {
    return { x: 0.5, y: 0.5 };
  }
  let sumX = 0;
  let sumY = 0;
  for (const pt of polygon) {
    sumX += pt.x || 0;
    sumY += pt.y || 0;
  }
  return {
    x: Number((sumX / polygon.length).toFixed(4)),
    y: Number((sumY / polygon.length).toFixed(4))
  };
}

/**
 * Computes signed polygon area using the shoelace formula.
 */
export function computePolygonArea(polygon) {
  if (!Array.isArray(polygon) || polygon.length < 3) return 0;
  let area = 0;
  const n = polygon.length;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    area += polygon[i].x * polygon[j].y;
    area -= polygon[j].x * polygon[i].y;
  }
  return Math.abs(area) / 2.0;
}

/**
 * Helper: Orientation test for 3 points (p, q, r).
 * 0 -> collinear, 1 -> clockwise, 2 -> counterclockwise.
 */
function ccwOrientation(p, q, r) {
  const val = (q.y - p.y) * (r.x - q.x) - (q.x - p.x) * (r.y - q.y);
  if (Math.abs(val) < 1e-9) return 0;
  return val > 0 ? 1 : 2;
}

/**
 * Helper: Checks if point q lies on segment pr.
 */
function onSegment(p, q, r) {
  return (
    q.x <= Math.max(p.x, r.x) + 1e-9 &&
    q.x >= Math.min(p.x, r.x) - 1e-9 &&
    q.y <= Math.max(p.y, r.y) + 1e-9 &&
    q.y >= Math.min(p.y, r.y) - 1e-9
  );
}

/**
 * Checks if line segment p1q1 intersects line segment p2q2.
 */
export function doSegmentsIntersect(p1, q1, p2, q2) {
  const o1 = ccwOrientation(p1, q1, p2);
  const o2 = ccwOrientation(p1, q1, q2);
  const o3 = ccwOrientation(p2, q2, p1);
  const o4 = ccwOrientation(p2, q2, q1);

  if (o1 !== o2 && o3 !== o4) {
    return true;
  }

  if (o1 === 0 && onSegment(p1, p2, q1)) return true;
  if (o2 === 0 && onSegment(p1, q2, q1)) return true;
  if (o3 === 0 && onSegment(p2, p1, q2)) return true;
  if (o4 === 0 && onSegment(p2, q1, q2)) return true;

  return false;
}

/**
 * Checks if a polygon's edges self-intersect (e.g. figure-8 bowtie).
 */
export function isPolygonSelfIntersecting(polygon) {
  if (!Array.isArray(polygon) || polygon.length < 4) return false;
  const n = polygon.length;

  for (let i = 0; i < n; i++) {
    const a1 = polygon[i];
    const a2 = polygon[(i + 1) % n];

    for (let j = i + 1; j < n; j++) {
      // Skip adjacent edges and the closing edge connecting back to first vertex
      if (Math.abs(i - j) <= 1 || (i === 0 && j === n - 1)) {
        continue;
      }
      const b1 = polygon[j];
      const b2 = polygon[(j + 1) % n];

      if (doSegmentsIntersect(a1, a2, b1, b2)) {
        return true;
      }
    }
  }
  return false;
}

/**
 * Comprehensive client-side validation of a single polygon.
 */
export function validatePolygon(polygon) {
  if (!Array.isArray(polygon)) {
    return { isValid: false, error: 'Polygon must be an array of vertices' };
  }

  if (polygon.length < 3) {
    return {
      isValid: false,
      error: `Polygon has only ${polygon.length} vertices; at least 3 vertices are required to define a zone`
    };
  }

  for (let i = 0; i < polygon.length; i++) {
    const pt = polygon[i];
    if (!pt || typeof pt !== 'object') {
      return { isValid: false, error: `Vertex at index ${i} is not a valid coordinate object` };
    }
    const x = Number(pt.x);
    const y = Number(pt.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      return { isValid: false, error: `Vertex at index ${i} has non-finite coordinates` };
    }
    if (x < 0 || x > 1 || y < 0 || y > 1) {
      return { isValid: false, error: `Vertex at index ${i} is out of bounds [0, 1]` };
    }
  }

  // Check duplicate consecutive vertices
  const n = polygon.length;
  for (let i = 0; i < n; i++) {
    const nextIdx = (i + 1) % n;
    const dx = Math.abs(polygon[i].x - polygon[nextIdx].x);
    const dy = Math.abs(polygon[i].y - polygon[nextIdx].y);
    if (dx < 1e-4 && dy < 1e-4) {
      return {
        isValid: false,
        error: `Polygon has zero-length edge between vertices ${i} and ${nextIdx}`
      };
    }
  }

  // Check self-intersection (figure-8 / bowtie)
  if (isPolygonSelfIntersecting(polygon)) {
    return {
      isValid: false,
      error: 'Self-intersecting polygon: boundary edges cross each other'
    };
  }

  // Check degenerate / zero area
  const area = computePolygonArea(polygon);
  if (area < 1e-5) {
    return {
      isValid: false,
      error: 'Polygon has zero or degenerate area'
    };
  }

  return { isValid: true, error: null };
}

/**
 * Validates complete camera-zone mappings list before submitting to backend.
 */
export function validateCameraZoneMappings(mappings, availableZones = []) {
  if (!Array.isArray(mappings)) {
    return { isValid: false, error: 'Zone configuration must be an array' };
  }

  const seenZones = new Set();
  const availableZoneIds = new Set(availableZones.map((z) => String(z._id || z.id)));

  for (let idx = 0; idx < mappings.length; idx++) {
    const m = mappings[idx];
    if (!m || typeof m !== 'object') {
      return { isValid: false, error: `Zone mapping at index ${idx} is invalid` };
    }

    const zid = String(m.zoneId || '').trim();
    if (!zid) {
      return { isValid: false, error: `Zone mapping at index ${idx} is missing a zoneId` };
    }

    if (seenZones.has(zid)) {
      return { isValid: false, error: `Duplicate zone mapping for zone "${zid}" on this camera` };
    }
    seenZones.add(zid);

    if (availableZoneIds.size > 0 && !availableZoneIds.has(zid)) {
      return { isValid: false, error: `Referenced zone "${zid}" does not exist in factory zones` };
    }

    const priority = m.priority !== undefined ? Number(m.priority) : 1;
    if (!Number.isInteger(priority) || priority < 0) {
      return { isValid: false, error: `Priority for zone "${zid}" must be a non-negative integer` };
    }

    const polyRes = validatePolygon(m.polygon);
    if (!polyRes.isValid) {
      return { isValid: false, error: `Zone "${zid}": ${polyRes.error}` };
    }
  }

  return { isValid: true, error: null };
}

/**
 * Role-based authorization: only Administrator / Super Admin can edit camera polygons.
 * Zone Supervisors have read-only access.
 */
export function canEditCameraPolygons(user) {
  if (!user || !user.role) return false;
  const rawRole = String(user.role).trim().toUpperCase();
  return ['SUPER_ADMIN', 'ADMIN', 'SUPERADMIN'].includes(rawRole);
}
