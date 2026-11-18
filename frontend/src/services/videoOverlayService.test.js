import test from 'node:test';
import assert from 'node:assert/strict';
import {
  findNearestFrame,
  formatVideoTime,
  getComplianceBadgeStyle,
  getPpeBadgeStyle,
  computeLetterboxedDimensions,
  scaleBoundingBox,
  isPlaybackAheadOfAnalysis
} from './videoOverlayService.js';

test('1. Timestamp to Nearest Frame Selection', async (t) => {
  const mockFrames = [
    { frame_idx: 1, timestamp_sec: 0.0, compliance_status: 'COMPLIANT' },
    { frame_idx: 2, timestamp_sec: 1.0, compliance_status: 'COMPLIANT' },
    { frame_idx: 3, timestamp_sec: 2.0, compliance_status: 'COMPLIANT' },
    { frame_idx: 4, timestamp_sec: 3.0, compliance_status: 'VIOLATION' },
    { frame_idx: 5, timestamp_sec: 4.0, compliance_status: 'VIOLATION' }
  ];

  await t.test('Handles empty and invalid frame arrays', () => {
    assert.equal(findNearestFrame(1.5, []), null);
    assert.equal(findNearestFrame(1.5, null), null);
    assert.equal(findNearestFrame(1.5, undefined), null);
  });

  await t.test('Exact timestamp match', () => {
    const res = findNearestFrame(2.0, mockFrames);
    assert.equal(res.frame_idx, 3);
    assert.equal(res._index, 2);
    assert.equal(res._timeDiff, 0);
  });

  await t.test('Interpolates to nearest neighbor within interval', () => {
    // 1.2s is closer to 1.0s than to 2.0s
    const resNear1 = findNearestFrame(1.2, mockFrames);
    assert.equal(resNear1.frame_idx, 2);

    // 1.8s is closer to 2.0s than to 1.0s
    const resNear2 = findNearestFrame(1.8, mockFrames);
    assert.equal(resNear2.frame_idx, 3);
  });

  await t.test('Clamps timestamps before start or after end', () => {
    const beforeStart = findNearestFrame(-5.0, mockFrames);
    assert.equal(beforeStart.frame_idx, 1);

    const afterEnd = findNearestFrame(100.0, mockFrames);
    assert.equal(afterEnd.frame_idx, 5);
  });
});

test('2. Time Formatter', async (t) => {
  await t.test('Formats seconds into standard time strings', () => {
    assert.equal(formatVideoTime(0), '0:00');
    assert.equal(formatVideoTime(9), '0:09');
    assert.equal(formatVideoTime(65), '1:05');
    assert.equal(formatVideoTime(3600), '1:00:00');
    assert.equal(formatVideoTime(3665), '1:01:05');
    assert.equal(formatVideoTime(-10), '0:00');
    assert.equal(formatVideoTime(NaN), '0:00');
  });
});

test('3. Compliance Badge Palette', async (t) => {
  await t.test('Returns appropriate tokens for COMPLIANT, VIOLATION, UNCERTAIN', () => {
    const c = getComplianceBadgeStyle('COMPLIANT');
    assert.equal(c.stroke, '#10b981');

    const v = getComplianceBadgeStyle('VIOLATION');
    assert.equal(v.stroke, '#f43f5e');

    const u = getComplianceBadgeStyle('UNCERTAIN');
    assert.equal(u.stroke, '#f59e0b');

    // Case insensitivity
    const lower = getComplianceBadgeStyle('violation');
    assert.equal(lower.stroke, '#f43f5e');
  });
});

test('4. Letterbox Geometry & Scaling Calculations', async (t) => {
  await t.test('Identical aspect ratio yields 0 offset', () => {
    // 1920x1080 in 960x540 container (both 16:9)
    const geom = computeLetterboxedDimensions(960, 540, 1920, 1080);
    assert.equal(geom.offsetX, 0);
    assert.equal(geom.offsetY, 0);
    assert.equal(geom.renderedWidth, 960);
    assert.equal(geom.renderedHeight, 540);
    assert.equal(geom.scale, 0.5);
    assert.equal(geom.isPortrait, false);
  });

  await t.test('Landscape video in taller container creates vertical letterbox (black bars top/bottom)', () => {
    // 16:9 video (1920x1080) in square container (800x800)
    const geom = computeLetterboxedDimensions(800, 800, 1920, 1080);
    assert.equal(geom.renderedWidth, 800);
    assert.equal(geom.scale, 800 / 1920);
    assert.equal(geom.renderedHeight, Math.round(1080 * (800 / 1920))); // 450px
    assert.equal(geom.offsetX, 0);
    assert.equal(geom.offsetY, (800 - 450) / 2); // 175px
    assert.equal(geom.isPortrait, false);
  });

  await t.test('Portrait 4K video (2160x3840) in 16:9 container creates horizontal pillarbox (black bars left/right)', () => {
    // 2160x3840 (portrait) in 1920x1080 container
    const geom = computeLetterboxedDimensions(1920, 1080, 2160, 3840);
    assert.equal(geom.isPortrait, true);
    // Vertical fits height: 1080
    assert.equal(geom.renderedHeight, 1080);
    assert.equal(geom.scale, 1080 / 3840);
    const expectedWidth = Math.round(2160 * (1080 / 3840)); // 608px
    assert.equal(geom.renderedWidth, expectedWidth);
    assert.equal(geom.offsetY, 0);
    assert.equal(geom.offsetX, (1920 - expectedWidth) / 2); // ~656px
  });
});

test('5. Bounding Box Screen Space Projection', async (t) => {
  await t.test('Scales native bounding box correctly with offsets', () => {
    const letterbox = {
      scale: 0.5,
      offsetX: 100,
      offsetY: 50
    };

    // Native box: [x1=200, y1=100, x2=600, y2=500] (w=400, h=400)
    const nativeBox = [200, 100, 600, 500];
    const projected = scaleBoundingBox(nativeBox, letterbox);

    assert.equal(projected.x, 200 * 0.5 + 100); // 200
    assert.equal(projected.y, 100 * 0.5 + 50);  // 100
    assert.equal(projected.width, 400 * 0.5);   // 200
    assert.equal(projected.height, 400 * 0.5);  // 200
  });

  await t.test('Gracefully rejects invalid bounding boxes', () => {
    assert.equal(scaleBoundingBox(null, {}), null);
    assert.equal(scaleBoundingBox([], {}), null);
    assert.equal(scaleBoundingBox([10, 20], {}), null);
  });
});

test('6. Stale Overlay & Analysis Lag Detection', async (t) => {
  await t.test('Returns false if analysis is not actively running', () => {
    assert.equal(isPlaybackAheadOfAnalysis(10.0, 2.0, false), false);
  });

  await t.test('Returns false when playback is within tolerance of analyzed front', () => {
    // Current time 2.4s, analyzed up to 2.0s, tolerance 0.8s -> not ahead
    assert.equal(isPlaybackAheadOfAnalysis(2.4, 2.0, true, 0.8), false);
  });

  await t.test('Returns true when playback head seeks ahead of analysis front', () => {
    // Current time 5.0s, analyzed up to 2.0s, tolerance 0.8s -> 5.0 > 2.8 -> ahead (stale)
    assert.equal(isPlaybackAheadOfAnalysis(5.0, 2.0, true, 0.8), true);
  });
});

test('7. PPE Equipment Badge Palette', async (t) => {
  await t.test('Returns electric cyan for helmet and default PPE', () => {
    const helmet = getPpeBadgeStyle('helmet');
    assert.equal(helmet.stroke, '#00e5ff');
    assert.equal(helmet.tagBg, '#00e5ff');
    assert.equal(helmet.textFill, '#000000');

    const generic = getPpeBadgeStyle('unknown_gear');
    assert.equal(generic.stroke, '#00e5ff');
  });

  await t.test('Returns safety yellow for vest', () => {
    const vest = getPpeBadgeStyle('safety vest');
    assert.equal(vest.stroke, '#facc15');
    assert.equal(vest.tagBg, '#facc15');
  });

  await t.test('Returns violet for boots and shoes', () => {
    const boots = getPpeBadgeStyle('boots');
    assert.equal(boots.stroke, '#c084fc');
    const shoes = getPpeBadgeStyle('safety_shoe');
    assert.equal(shoes.stroke, '#c084fc');
  });

  await t.test('Returns sky blue for goggles and glasses', () => {
    const goggles = getPpeBadgeStyle('goggles');
    assert.equal(goggles.stroke, '#38bdf8');
  });
});
