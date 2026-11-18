/**
 * Video Overlay & Native Playback Synchronization Service
 * Milestone M1: Handles timestamp-to-frame interpolation, letterbox geometry,
 * bounding box coordinate transformations, and compliance visual styling.
 */

/**
 * Finds the nearest processed frame in frame_breakdown for a given playback timestamp.
 * Performs a fast nearest-neighbor search based on timestamp_sec.
 * 
 * @param {number} currentTime - Current video playback timestamp in seconds.
 * @param {Array<Object>} frameBreakdown - Array of frame records from /detect-video.
 * @returns {Object|null} The closest frame object along with its index, or null if empty.
 */
export function findNearestFrame(currentTime, frameBreakdown) {
  if (!Array.isArray(frameBreakdown) || frameBreakdown.length === 0) {
    return null;
  }

  const validTime = Math.max(0, Number(currentTime) || 0);

  let bestIndex = 0;
  let minDiff = Math.abs((Number(frameBreakdown[0].timestamp_sec) || 0) - validTime);

  for (let i = 1; i < frameBreakdown.length; i++) {
    const frameTime = Number(frameBreakdown[i].timestamp_sec) || 0;
    const diff = Math.abs(frameTime - validTime);
    if (diff < minDiff) {
      minDiff = diff;
      bestIndex = i;
    }
  }

  return {
    ...frameBreakdown[bestIndex],
    _index: bestIndex,
    _timeDiff: minDiff
  };
}

/**
 * Formats a duration in seconds into MM:SS or HH:MM:SS format.
 * 
 * @param {number} seconds - Time duration in seconds.
 * @returns {string} Formatted timestamp string (e.g. "01:24" or "0:05").
 */
export function formatVideoTime(seconds) {
  if (isNaN(seconds) || seconds < 0) return '0:00';
  const totalSecs = Math.floor(seconds);
  const hrs = Math.floor(totalSecs / 3600);
  const mins = Math.floor((totalSecs % 3600) / 60);
  const secs = totalSecs % 60;

  if (hrs > 0) {
    return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Returns color palette definitions for compliance status badges and bounding boxes.
 * 
 * @param {string} status - Compliance status string ('COMPLIANT', 'VIOLATION', 'UNCERTAIN').
 * @returns {Object} Colors and styling tokens.
 */
export function getComplianceBadgeStyle(status) {
  const norm = (status || '').toUpperCase().trim();
  switch (norm) {
    case 'COMPLIANT':
      return {
        status: 'COMPLIANT',
        stroke: '#10b981', // emerald-500
        fill: 'rgba(16, 185, 129, 0.15)',
        textFill: '#ffffff',
        badgeBg: 'bg-emerald-950',
        badgeText: 'text-emerald-400',
        badgeBorder: 'border-emerald-800'
      };
    case 'VIOLATION':
      return {
        status: 'VIOLATION',
        stroke: '#f43f5e', // rose-500
        fill: 'rgba(244, 63, 94, 0.18)',
        textFill: '#ffffff',
        badgeBg: 'bg-rose-950',
        badgeText: 'text-rose-400',
        badgeBorder: 'border-rose-800'
      };
    case 'UNCERTAIN':
    default:
      return {
        status: 'UNCERTAIN',
        stroke: '#f59e0b', // amber-500
        fill: 'rgba(245, 158, 11, 0.15)',
        textFill: '#ffffff',
        badgeBg: 'bg-amber-950',
        badgeText: 'text-amber-400',
        badgeBorder: 'border-amber-800'
      };
  }
}

/**
 * Returns color palette definitions and SVG styling tokens for individual PPE equipment classes.
 * Follows the existing webcam detection visual style:
 * - Electric Cyan (#00e5ff) baseline with high-contrast text and labels
 * - Class-specific distinctive tokens:
 *   - Helmet: Electric Cyan (#00e5ff)
 *   - Vest: Safety Yellow (#facc15)
 *   - Boots/Shoes: Violet (#c084fc)
 *   - Goggles/Glasses: Sky Blue (#38bdf8)
 *   - Gloves: Teal (#2dd4bf)
 *   - Mask/Respirator: Pink (#f472b6)
 * 
 * @param {string} className - Detected PPE item class name (e.g. 'helmet', 'vest', 'boots').
 * @returns {Object} Styling tokens { stroke, fill, tagBg, textFill }
 */
export function getPpeBadgeStyle(className) {
  const norm = (className || '').toLowerCase().trim();
  let stroke = '#00e5ff'; // Electric Cyan (Webcam convention)
  let fill = 'rgba(0, 229, 255, 0.12)';
  let tagBg = '#00e5ff';
  let textFill = '#000000';

  if (norm.includes('vest')) {
    stroke = '#facc15'; // Safety Yellow
    fill = 'rgba(250, 204, 21, 0.14)';
    tagBg = '#facc15';
    textFill = '#000000';
  } else if (norm.includes('boot') || norm.includes('shoe') || norm.includes('footwear')) {
    stroke = '#c084fc'; // Violet
    fill = 'rgba(192, 132, 252, 0.14)';
    tagBg = '#c084fc';
    textFill = '#000000';
  } else if (norm.includes('goggle') || norm.includes('glass')) {
    stroke = '#38bdf8'; // Sky Blue
    fill = 'rgba(56, 189, 248, 0.14)';
    tagBg = '#38bdf8';
    textFill = '#000000';
  } else if (norm.includes('glove')) {
    stroke = '#2dd4bf'; // Teal
    fill = 'rgba(45, 212, 191, 0.14)';
    tagBg = '#2dd4bf';
    textFill = '#000000';
  } else if (norm.includes('mask') || norm.includes('respirator')) {
    stroke = '#f472b6'; // Pink
    fill = 'rgba(244, 114, 182, 0.14)';
    tagBg = '#f472b6';
    textFill = '#000000';
  }

  return { stroke, fill, tagBg, textFill };
}

/**
 * Computes exact letterbox geometry for HTML5 <video> with `object-fit: contain`
 * inside a container of known dimensions.
 * 
 * @param {number} containerWidth - Outer player container width in px.
 * @param {number} containerHeight - Outer player container height in px.
 * @param {number} videoWidth - Intrinsic video width in px (e.g. 2160 or 1920).
 * @param {number} videoHeight - Intrinsic video height in px (e.g. 3840 or 1080).
 * @returns {Object} Rendered sub-rectangle { renderedWidth, renderedHeight, offsetX, offsetY, scale, isPortrait }
 */
export function computeLetterboxedDimensions(containerWidth, containerHeight, videoWidth, videoHeight) {
  const cW = Math.max(1, Number(containerWidth) || 640);
  const cH = Math.max(1, Number(containerHeight) || 360);
  const vW = Math.max(1, Number(videoWidth) || 1920);
  const vH = Math.max(1, Number(videoHeight) || 1080);

  const containerAspect = cW / cH;
  const videoAspect = vW / vH;

  let scale;
  let renderedWidth;
  let renderedHeight;
  let offsetX;
  let offsetY;

  if (videoAspect > containerAspect) {
    // Letterbox on top & bottom (wider than container aspect)
    scale = cW / vW;
    renderedWidth = cW;
    renderedHeight = vH * scale;
    offsetX = 0;
    offsetY = (cH - renderedHeight) / 2;
  } else {
    // Pillarbox on left & right (taller/narrower than container aspect, e.g. portrait)
    scale = cH / vH;
    renderedWidth = vW * scale;
    renderedHeight = cH;
    offsetX = (cW - renderedWidth) / 2;
    offsetY = 0;
  }

  return {
    renderedWidth: Math.round(renderedWidth),
    renderedHeight: Math.round(renderedHeight),
    offsetX: Math.round(offsetX),
    offsetY: Math.round(offsetY),
    scale,
    isPortrait: vH > vW
  };
}

/**
 * Projects a 2D bounding box [x1, y1, x2, y2] from intrinsic video coordinates
 * to rendered letterboxed screen space.
 * 
 * @param {Array<number>} bbox - [x1, y1, x2, y2] in native video coordinates.
 * @param {Object} letterbox - Geometry object returned by computeLetterboxedDimensions.
 * @returns {Object|null} Scaled box { x, y, width, height } in container coordinates.
 */
export function scaleBoundingBox(bbox, letterbox) {
  if (!Array.isArray(bbox) || bbox.length < 4) return null;
  const { scale = 1, offsetX = 0, offsetY = 0 } = letterbox || {};

  const x1 = Math.round(bbox[0] * scale + offsetX);
  const y1 = Math.round(bbox[1] * scale + offsetY);
  const x2 = Math.round(bbox[2] * scale + offsetX);
  const y2 = Math.round(bbox[3] * scale + offsetY);

  const width = Math.max(1, x2 - x1);
  const height = Math.max(1, y2 - y1);

  return { x: x1, y: y1, width, height };
}

/**
 * Determines whether the active frame is stale relative to playback time.
 * If playback is actively running ahead of analysis front, returns true.
 * 
 * @param {number} currentTime - Current video playback timestamp in seconds.
 * @param {number} latestAnalyzedTime - Highest timestamp analyzed so far.
 * @param {boolean} isAnalyzing - Whether progressive analysis is currently running.
 * @param {number} [toleranceSec=0.8] - Max acceptable gap before marking stale.
 * @returns {boolean} True if playback head is ahead of the analysis front.
 */
export function isPlaybackAheadOfAnalysis(currentTime, latestAnalyzedTime, isAnalyzing, toleranceSec = 0.8) {
  if (!isAnalyzing) return false;
  return Number(currentTime) > Number(latestAnalyzedTime) + Number(toleranceSec);
}
