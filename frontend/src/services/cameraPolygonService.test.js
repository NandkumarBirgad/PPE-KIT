import test from 'node:test';
import assert from 'node:assert/strict';

import {
  toNormalizedCoord,
  toScreenCoord,
  formatSvgPoints,
  computePolygonCentroid,
  computePolygonArea,
  doSegmentsIntersect,
  isPolygonSelfIntersecting,
  validatePolygon,
  validateCameraZoneMappings,
  canEditCameraPolygons,
  getZoneColor,
  ZONE_PALETTE
} from './cameraPolygonService.js';

test('1. Normalized coordinate conversion clamped to [0, 1]', () => {
  const containerRect = { left: 100, top: 50, width: 800, height: 600 };

  // Center click
  const center = toNormalizedCoord({ clientX: 500, clientY: 350 }, containerRect);
  assert.equal(center.x, 0.5);
  assert.equal(center.y, 0.5);

  // Top-left click
  const topLeft = toNormalizedCoord({ clientX: 100, clientY: 50 }, containerRect);
  assert.equal(topLeft.x, 0);
  assert.equal(topLeft.y, 0);

  // Bottom-right click
  const bottomRight = toNormalizedCoord({ clientX: 900, clientY: 650 }, containerRect);
  assert.equal(bottomRight.x, 1);
  assert.equal(bottomRight.y, 1);

  // Out of bounds clamp (left & above)
  const clampedMin = toNormalizedCoord({ clientX: 10, clientY: -20 }, containerRect);
  assert.equal(clampedMin.x, 0);
  assert.equal(clampedMin.y, 0);

  // Out of bounds clamp (right & below)
  const clampedMax = toNormalizedCoord({ clientX: 1200, clientY: 1000 }, containerRect);
  assert.equal(clampedMax.x, 1);
  assert.equal(clampedMax.y, 1);
});

test('2. Screen pixel coordinate conversion scales accurately with resizing', () => {
  const normPoint = { x: 0.25, y: 0.75 };

  // 640x480 resolution display
  const res1 = toScreenCoord(normPoint, { width: 640, height: 480 });
  assert.equal(res1.px, 160);
  assert.equal(res1.py, 360);

  // Resized to 1280x960 resolution display (same normalized point overlays exact physical location)
  const res2 = toScreenCoord(normPoint, { width: 1280, height: 960 });
  assert.equal(res2.px, 320);
  assert.equal(res2.py, 720);

  // High-precision SVG points string formatting
  const poly = [{ x: 0.1, y: 0.2 }, { x: 0.8, y: 0.2 }, { x: 0.8, y: 0.9 }];
  const svgPts = formatSvgPoints(poly, 1000);
  assert.equal(svgPts, '100.00,200.00 800.00,200.00 800.00,900.00');
});

test('3. Computes polygon centroid and non-zero area correctly', () => {
  // Rectangle in center: [0.2, 0.2] to [0.8, 0.8]
  const rectPoly = [
    { x: 0.2, y: 0.2 },
    { x: 0.8, y: 0.2 },
    { x: 0.8, y: 0.8 },
    { x: 0.2, y: 0.8 }
  ];

  const centroid = computePolygonCentroid(rectPoly);
  assert.equal(centroid.x, 0.5);
  assert.equal(centroid.y, 0.5);

  const area = computePolygonArea(rectPoly);
  assert.ok(Math.abs(area - 0.36) < 1e-4);
});

test('4. Detects line segment intersection and self-intersecting bowtie polygons', () => {
  // Crossing segments (X shape)
  const p1 = { x: 0, y: 0 };
  const q1 = { x: 1, y: 1 };
  const p2 = { x: 0, y: 1 };
  const q2 = { x: 1, y: 0 };
  assert.equal(doSegmentsIntersect(p1, q1, p2, q2), true);

  // Parallel non-intersecting segments
  const p3 = { x: 0, y: 0 };
  const q3 = { x: 1, y: 0 };
  const p4 = { x: 0, y: 1 };
  const q4 = { x: 1, y: 1 };
  assert.equal(doSegmentsIntersect(p3, q3, p4, q4), false);

  // Self-intersecting bowtie polygon
  const bowtie = [
    { x: 0.1, y: 0.1 },
    { x: 0.9, y: 0.9 },
    { x: 0.9, y: 0.1 },
    { x: 0.1, y: 0.9 }
  ];
  assert.equal(isPolygonSelfIntersecting(bowtie), true);

  // Valid non-intersecting convex polygon
  const validSquare = [
    { x: 0.1, y: 0.1 },
    { x: 0.9, y: 0.1 },
    { x: 0.9, y: 0.9 },
    { x: 0.1, y: 0.9 }
  ];
  assert.equal(isPolygonSelfIntersecting(validSquare), false);
});

test('5. Validates individual polygon vertices, counts, and boundary constraints', () => {
  // Fewer than 3 vertices rejected
  const twoPoints = [{ x: 0.1, y: 0.1 }, { x: 0.5, y: 0.5 }];
  const resFew = validatePolygon(twoPoints);
  assert.equal(resFew.isValid, false);
  assert.match(resFew.error, /at least 3 vertices/i);

  // Duplicate consecutive vertices rejected
  const dupConsecutive = [
    { x: 0.1, y: 0.1 },
    { x: 0.1, y: 0.1 },
    { x: 0.8, y: 0.5 }
  ];
  const resDup = validatePolygon(dupConsecutive);
  assert.equal(resDup.isValid, false);
  assert.match(resDup.error, /zero-length edge/i);

  // Zero-length closing edge rejected
  const zeroClosing = [
    { x: 0.2, y: 0.2 },
    { x: 0.7, y: 0.2 },
    { x: 0.2, y: 0.2 }
  ];
  const resClosing = validatePolygon(zeroClosing);
  assert.equal(resClosing.isValid, false);

  // Bowtie polygon rejected
  const bowtie = [
    { x: 0.1, y: 0.1 },
    { x: 0.9, y: 0.9 },
    { x: 0.9, y: 0.1 },
    { x: 0.1, y: 0.9 }
  ];
  const resBowtie = validatePolygon(bowtie);
  assert.equal(resBowtie.isValid, false);
  assert.match(resBowtie.error, /self-intersecting/i);

  // Valid triangle accepted
  const validTriangle = [
    { x: 0.1, y: 0.1 },
    { x: 0.8, y: 0.2 },
    { x: 0.4, y: 0.9 }
  ];
  const resTri = validatePolygon(validTriangle);
  assert.equal(resTri.isValid, true);
  assert.equal(resTri.error, null);
});

test('6. Validates complete camera-zone mappings (duplicate zones, non-existent zones, priorities)', () => {
  const availableZones = [
    { _id: 'zone_01', name: 'General Assembly' },
    { _id: 'zone_02', name: 'Welding Bay' }
  ];

  const validSquare = [
    { x: 0.1, y: 0.1 },
    { x: 0.4, y: 0.1 },
    { x: 0.4, y: 0.9 },
    { x: 0.1, y: 0.9 }
  ];

  // Valid mappings
  const validMappings = [
    { zoneId: 'zone_01', priority: 1, polygon: validSquare }
  ];
  const resValid = validateCameraZoneMappings(validMappings, availableZones);
  assert.equal(resValid.isValid, true);

  // Duplicate zone mapping on the same camera rejected
  const dupZones = [
    { zoneId: 'zone_01', priority: 1, polygon: validSquare },
    { zoneId: 'zone_01', priority: 2, polygon: validSquare }
  ];
  const resDup = validateCameraZoneMappings(dupZones, availableZones);
  assert.equal(resDup.isValid, false);
  assert.match(resDup.error, /duplicate zone mapping/i);

  // Non-existent zone rejected
  const unkZone = [
    { zoneId: 'zone_non_existent', priority: 1, polygon: validSquare }
  ];
  const resUnk = validateCameraZoneMappings(unkZone, availableZones);
  assert.equal(resUnk.isValid, false);
  assert.match(resUnk.error, /does not exist in factory zones/i);

  // Negative priority rejected
  const negPri = [
    { zoneId: 'zone_01', priority: -2, polygon: validSquare }
  ];
  const resNeg = validateCameraZoneMappings(negPri, availableZones);
  assert.equal(resNeg.isValid, false);
  assert.match(resNeg.error, /non-negative integer/i);
});

test('7. Enforces Administrator vs Zone Supervisor permissions', () => {
  // Administrator / Super Admin can edit
  assert.equal(canEditCameraPolygons({ role: 'admin' }), true);
  assert.equal(canEditCameraPolygons({ role: 'SUPER_ADMIN' }), true);
  assert.equal(canEditCameraPolygons({ role: 'superadmin' }), true);

  // Zone Supervisor / Reviewer has read-only access
  assert.equal(canEditCameraPolygons({ role: 'supervisor' }), false);
  assert.equal(canEditCameraPolygons({ role: 'ZONE_SUPERVISOR' }), false);
  assert.equal(canEditCameraPolygons({ role: 'reviewer' }), false);

  // Anonymous / null role cannot edit
  assert.equal(canEditCameraPolygons(null), false);
  assert.equal(canEditCameraPolygons({}), false);
});

test('8. Cycles distinct zone color palettes deterministically', () => {
  const c0 = getZoneColor(0);
  const c1 = getZoneColor(1);
  const c2 = getZoneColor(2);

  assert.equal(c0.name, 'Emerald');
  assert.equal(c1.name, 'Amber');
  assert.equal(c2.name, 'Sky');
  assert.notEqual(c0.stroke, c1.stroke);
});
