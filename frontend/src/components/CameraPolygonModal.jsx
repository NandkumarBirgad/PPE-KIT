import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Layers,
  X,
  Plus,
  Trash2,
  Save,
  RotateCcw,
  Upload,
  AlertTriangle,
  CheckCircle2,
  Info,
  Maximize2,
  ShieldAlert,
  Eye,
  Sliders,
  Camera,
  CornerDownLeft,
  Undo2
} from 'lucide-react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import {
  getZoneColor,
  toNormalizedCoord,
  formatSvgPoints,
  computePolygonCentroid,
  validatePolygon,
  validateCameraZoneMappings,
  canEditCameraPolygons
} from '../services/cameraPolygonService';

export default function CameraPolygonModal({
  camera,
  allCameras = [],
  availableZones = [],
  onClose,
  onSaved,
  initialReferenceImageUrl = null
}) {
  const { user } = useAuth();
  const isAdmin = canEditCameraPolygons(user);

  const [activeCameraId, setActiveCameraId] = useState(camera?._id || '');
  const [activeCamera, setActiveCamera] = useState(camera);
  const [configuredZones, setConfiguredZones] = useState([]);
  const [selectedZoneId, setSelectedZoneId] = useState(null);

  // Drawing state
  const [isDrawing, setIsDrawing] = useState(false);
  const [drawingPoints, setDrawingPoints] = useState([]);
  const [drawingTargetZoneId, setDrawingTargetZoneId] = useState(null);
  const [currentCursorNorm, setCurrentCursorNorm] = useState(null);

  // Dragging vertex state
  const [dragState, setDragState] = useState(null); // { zoneId, vertexIndex }

  // Reference image
  const [referenceImageUrl, setReferenceImageUrl] = useState(initialReferenceImageUrl);
  const [imageAspectRatio, setImageAspectRatio] = useState('16 / 9');

  // Status & messages
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [validationError, setValidationError] = useState('');
  const [successToast, setSuccessToast] = useState('');

  const containerRef = useRef(null);
  const fileInputRef = useRef(null);

  // Find camera object when activeCameraId changes
  useEffect(() => {
    const cam = allCameras.find((c) => String(c._id) === String(activeCameraId)) || camera;
    setActiveCamera(cam);
    if (cam) {
      loadCameraPolygons(cam._id);
    }
  }, [activeCameraId]);

  // Load existing camera zones from backend
  const loadCameraPolygons = async (camId) => {
    if (!camId) return;
    setLoading(true);
    setValidationError('');
    try {
      const res = await api.get(`/cameras/${camId}/zones`);
      const rawZones = Array.isArray(res.data) ? res.data : [];
      setConfiguredZones(rawZones);
      if (rawZones.length > 0) {
        setSelectedZoneId(rawZones[0].zoneId);
      } else {
        setSelectedZoneId(null);
      }
    } catch (err) {
      console.error('Error loading camera polygons:', err);
      setValidationError(err.response?.data?.message || 'Failed to fetch camera zone polygons');
    } finally {
      setLoading(false);
    }
  };

  // Switch camera
  const handleCameraChange = (e) => {
    const newId = e.target.value;
    if (isDrawing && !window.confirm('Discard current in-progress polygon and switch camera?')) {
      return;
    }
    cancelDrawing();
    setActiveCameraId(newId);
  };

  // Reference image upload
  const handleImageUpload = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      const url = URL.createObjectURL(file);
      setReferenceImageUrl(url);
      const img = new Image();
      img.onload = () => {
        if (img.width && img.height) {
          setImageAspectRatio(`${img.width} / ${img.height}`);
        }
      };
      img.src = url;
    }
  };

  // Convert pointer to normalized coordinates [0, 1]
  const getNormFromPointer = (e) => {
    if (!containerRef.current) return { x: 0, y: 0 };
    const rect = containerRef.current.getBoundingClientRect();
    return toNormalizedCoord(e, rect);
  };

  // Start drawing a polygon for a specific zone
  const startDrawing = (zoneId) => {
    if (!isAdmin) return;
    const existing = configuredZones.find((z) => String(z.zoneId) === String(zoneId));
    if (existing) {
      if (!window.confirm(`Zone "${existing.zoneName || zoneId}" already has a polygon. Redraw it?`)) {
        return;
      }
      setConfiguredZones((prev) => prev.filter((z) => String(z.zoneId) !== String(zoneId)));
    }
    setIsDrawing(true);
    setDrawingPoints([]);
    setDrawingTargetZoneId(zoneId);
    setSelectedZoneId(zoneId);
    setValidationError('');
  };

  // Add vertex during drawing
  const handleSvgClick = (e) => {
    if (!isDrawing || !isAdmin) return;
    const pt = getNormFromPointer(e);

    // If we have >= 3 points and user clicks very close to first vertex, snap and complete
    if (drawingPoints.length >= 3) {
      const first = drawingPoints[0];
      const dist = Math.hypot(pt.x - first.x, pt.y - first.y);
      if (dist < 0.035) {
        completeDrawing();
        return;
      }
    }

    setDrawingPoints((prev) => [...prev, pt]);
  };

  // Complete drawing explicitly
  const completeDrawing = () => {
    if (!isDrawing) return;
    if (drawingPoints.length < 3) {
      setValidationError('A polygon must contain at least 3 vertices before it can be closed.');
      return;
    }

    const polyValidation = validatePolygon(drawingPoints);
    if (!polyValidation.isValid) {
      setValidationError(polyValidation.error);
      return;
    }

    const zoneObj = availableZones.find((z) => String(z._id || z.id) === String(drawingTargetZoneId));
    const newMapping = {
      zoneId: String(drawingTargetZoneId),
      zoneName: zoneObj?.name || `Zone ${drawingTargetZoneId}`,
      priority: 1,
      polygon: drawingPoints
    };

    setConfiguredZones((prev) => [...prev, newMapping]);
    setIsDrawing(false);
    setDrawingPoints([]);
    setDrawingTargetZoneId(null);
    setSelectedZoneId(newMapping.zoneId);
    setValidationError('');
    setSuccessToast(`Polygon for "${newMapping.zoneName}" completed! Click "Save Zone Polygons" to persist.`);
    setTimeout(() => setSuccessToast(''), 4000);
  };

  // Cancel drawing
  const cancelDrawing = () => {
    setIsDrawing(false);
    setDrawingPoints([]);
    setDrawingTargetZoneId(null);
    setCurrentCursorNorm(null);
    setValidationError('');
  };

  // Undo last point
  const undoLastPoint = () => {
    setDrawingPoints((prev) => prev.slice(0, -1));
  };

  // Vertex Dragging handlers
  const handleVertexMouseDown = (e, zoneId, vertexIdx) => {
    if (!isAdmin || isDrawing) return;
    e.stopPropagation();
    setDragState({ zoneId, vertexIndex: vertexIdx });
  };

  const handlePointerMove = useCallback(
    (e) => {
      const norm = getNormFromPointer(e);
      if (isDrawing) {
        setCurrentCursorNorm(norm);
      }
      if (dragState) {
        const { zoneId, vertexIndex } = dragState;
        setConfiguredZones((prev) =>
          prev.map((mapping) => {
            if (String(mapping.zoneId) === String(zoneId)) {
              const updatedPoly = [...mapping.polygon];
              updatedPoly[vertexIndex] = norm;
              return { ...mapping, polygon: updatedPoly };
            }
            return mapping;
          })
        );
      }
    },
    [isDrawing, dragState]
  );

  const handlePointerUp = useCallback(() => {
    if (dragState) {
      // Validate the dragged polygon
      const mapping = configuredZones.find((m) => String(m.zoneId) === String(dragState.zoneId));
      if (mapping) {
        const check = validatePolygon(mapping.polygon);
        if (!check.isValid) {
          setValidationError(`Warning: ${check.error}`);
        } else {
          setValidationError('');
        }
      }
      setDragState(null);
    }
  }, [dragState, configuredZones]);

  useEffect(() => {
    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };
  }, [handlePointerMove, handlePointerUp]);

  // Delete polygon
  const handleDeletePolygon = (zoneId) => {
    if (!isAdmin) return;
    const target = configuredZones.find((z) => String(z.zoneId) === String(zoneId));
    const name = target?.zoneName || zoneId;
    if (window.confirm(`Are you sure you want to remove the polygon boundary for zone "${name}"?`)) {
      setConfiguredZones((prev) => prev.filter((z) => String(z.zoneId) !== String(zoneId)));
      if (selectedZoneId === zoneId) {
        setSelectedZoneId(null);
      }
      setSuccessToast(`Removed boundary for "${name}". Click "Save Zone Polygons" to persist.`);
      setTimeout(() => setSuccessToast(''), 4000);
    }
  };

  // Update polygon priority
  const handlePriorityChange = (zoneId, newPriority) => {
    if (!isAdmin) return;
    const priInt = parseInt(newPriority, 10);
    setConfiguredZones((prev) =>
      prev.map((m) => (String(m.zoneId) === String(zoneId) ? { ...m, priority: isNaN(priInt) ? 1 : Math.max(0, priInt) } : m))
    );
  };

  // Save changes to backend
  const handleSave = async () => {
    if (!isAdmin || !activeCamera) return;
    setSaving(true);
    setValidationError('');

    // Pre-flight client-side validation
    const clientValidation = validateCameraZoneMappings(configuredZones, availableZones);
    if (!clientValidation.isValid) {
      setValidationError(clientValidation.error);
      setSaving(false);
      return;
    }

    try {
      const payload = { zones: configuredZones };
      const res = await api.put(`/cameras/${activeCamera._id}/zones`, payload);
      setSuccessToast(`Successfully saved ${configuredZones.length} safety zone polygons for camera "${activeCamera.name}"!`);
      setTimeout(() => setSuccessToast(''), 5000);
      if (onSaved) onSaved(res.data);
    } catch (err) {
      console.error('Failed to save camera zone polygons:', err);
      setValidationError(err.response?.data?.message || 'Failed to save zone polygons to backend.');
    } finally {
      setSaving(false);
    }
  };

  // Selected polygon details
  const selectedMapping = configuredZones.find((m) => String(m.zoneId) === String(selectedZoneId));
  const selectedZoneInfo = availableZones.find((z) => String(z._id || z.id) === String(selectedZoneId));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 lg:p-6 bg-black/85 backdrop-blur-md animate-in fade-in">
      <div className="w-full max-w-6xl max-h-[94vh] bg-slate-900 border border-slate-800 rounded-3xl shadow-2xl flex flex-col overflow-hidden">
        {/* Top Header Bar */}
        <div className="p-4 lg:px-6 lg:py-4 border-b border-slate-800 bg-slate-950/80 flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-sky-950 border border-sky-800 text-sky-400 flex items-center justify-center font-bold shadow-lg shadow-sky-950/50">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-white tracking-tight">Camera Zone Polygon Calibration</h2>
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border ${
                  isAdmin
                    ? 'bg-sky-950/80 border-sky-800 text-sky-400'
                    : 'bg-amber-950/80 border-amber-800 text-amber-400'
                }`}>
                  {isAdmin ? 'Administrator (Authoritative)' : 'Zone Supervisor (Read-Only)'}
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Define camera-specific spatial polygon boundaries and overlap priorities for automated worker zone assignment
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Camera Switcher Dropdown */}
            {allCameras.length > 1 && (
              <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-xl">
                <Camera className="w-3.5 h-3.5 text-sky-400" />
                <span className="text-xs text-slate-400 font-medium">Camera:</span>
                <select
                  value={activeCameraId}
                  onChange={handleCameraChange}
                  className="bg-transparent text-xs text-white font-semibold focus:outline-none cursor-pointer"
                >
                  {allCameras.map((c) => (
                    <option key={c._id} value={c._id} className="bg-slate-900 text-white">
                      {c.name} ({c.resolution || '1080p'})
                    </option>
                  ))}
                </select>
              </div>
            )}

            <button
              onClick={onClose}
              className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition"
              title="Close Editor"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Action / Warning Notice Banners */}
        {validationError && (
          <div className="px-6 py-2.5 bg-rose-950/60 border-b border-rose-800/80 text-rose-200 text-xs flex items-center justify-between animate-in slide-in-from-top-2">
            <div className="flex items-center gap-2 font-medium">
              <AlertTriangle className="w-4 h-4 text-rose-400 flex-shrink-0" />
              <span>{validationError}</span>
            </div>
            <button onClick={() => setValidationError('')} className="text-rose-400 hover:text-white">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {successToast && (
          <div className="px-6 py-2.5 bg-emerald-950/60 border-b border-emerald-800/80 text-emerald-200 text-xs flex items-center justify-between animate-in slide-in-from-top-2">
            <div className="flex items-center gap-2 font-medium">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              <span>{successToast}</span>
            </div>
            <button onClick={() => setSuccessToast('')} className="text-emerald-400 hover:text-white">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {!isAdmin && (
          <div className="px-6 py-2 bg-amber-950/40 border-b border-amber-800/60 text-amber-200 text-xs flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-amber-400 flex-shrink-0" />
            <span>
              <strong>Read-Only Inspection Mode:</strong> You are signed in as a Zone Supervisor. Polygon vertices, priority mappings, and calibrations are displayed for verification but cannot be modified.
            </span>
          </div>
        )}

        {/* Main Content Area */}
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-4 overflow-hidden">
          {/* Canvas Viewport (3 Columns) */}
          <div className="lg:col-span-3 p-4 bg-slate-950/90 flex flex-col justify-between overflow-auto relative select-none">
            {/* Top Canvas Controls Bar */}
            <div className="flex items-center justify-between mb-3 text-xs">
              <div className="flex items-center gap-2">
                <span className="text-slate-400 font-medium">Active CCTV Perspective:</span>
                <span className="text-white font-bold">{activeCamera?.name || 'Live Camera Feed'}</span>
                <span className="text-[10px] text-slate-500 font-mono">({activeCamera?.resolution || '1080p'})</span>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleImageUpload}
                  accept="image/*"
                  className="hidden"
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-300 text-xs font-semibold transition"
                  title="Upload actual exported snapshot from this camera feed"
                >
                  <Upload className="w-3.5 h-3.5 text-sky-400" />
                  <span>{referenceImageUrl ? 'Change Reference Frame' : 'Load CCTV Snapshot'}</span>
                </button>

                {referenceImageUrl && (
                  <button
                    type="button"
                    onClick={() => {
                      setReferenceImageUrl(null);
                      setImageAspectRatio('16 / 9');
                    }}
                    className="px-2.5 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-400 hover:text-white text-xs transition"
                    title="Reset to perspective factory floor grid"
                  >
                    Reset Grid
                  </button>
                )}
              </div>
            </div>

            {/* Viewport Frame with Responsive Container */}
            <div className="flex-1 flex items-center justify-center min-h-[360px] max-h-[62vh] relative">
              <div
                ref={containerRef}
                style={{ aspectRatio: imageAspectRatio }}
                className="w-full max-h-full max-w-full relative rounded-2xl overflow-hidden border-2 border-slate-800 bg-slate-950 shadow-2xl flex items-center justify-center cursor-crosshair select-none"
                onClick={handleSvgClick}
              >
                {/* 1. Reference Image or High-Contrast Industrial Perspective Grid */}
                {referenceImageUrl ? (
                  <img
                    src={referenceImageUrl}
                    alt="Camera calibration reference"
                    className="w-full h-full object-fill select-none pointer-events-none"
                  />
                ) : (
                  <div className="w-full h-full relative bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 flex flex-col items-center justify-center pointer-events-none select-none">
                    {/* Perspective grid lines to guide calibration */}
                    <svg className="absolute inset-0 w-full h-full opacity-25" xmlns="http://www.w3.org/2000/svg">
                      <defs>
                        <pattern id="gridPattern" width="40" height="40" patternUnits="userSpaceOnUse">
                          <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#38bdf8" strokeWidth="0.8" />
                        </pattern>
                      </defs>
                      <rect width="100%" height="100%" fill="url(#gridPattern)" />
                      {/* Vanishing point guide lines */}
                      <line x1="0%" y1="0%" x2="50%" y2="35%" stroke="#38bdf8" strokeWidth="1" strokeDasharray="4 4" />
                      <line x1="100%" y1="0%" x2="50%" y2="35%" stroke="#38bdf8" strokeWidth="1" strokeDasharray="4 4" />
                      <line x1="0%" y1="100%" x2="50%" y2="35%" stroke="#38bdf8" strokeWidth="1.2" strokeDasharray="5 5" />
                      <line x1="100%" y1="100%" x2="50%" y2="35%" stroke="#38bdf8" strokeWidth="1.2" strokeDasharray="5 5" />
                    </svg>

                    <div className="text-center z-10 p-4">
                      <Camera className="w-10 h-10 text-slate-600 mx-auto mb-2 opacity-50" />
                      <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                        Camera Spatial Calibration Viewport (16:9 Aspect Ratio)
                      </p>
                      <p className="text-[11px] text-slate-500 mt-1 max-w-md">
                        Normalized coordinate plane [0, 1]. Click points to plot zone polygons, or load an actual CCTV frame using "Load CCTV Snapshot".
                      </p>
                    </div>
                  </div>
                )}

                {/* 2. Interactive SVG Polygon Layer */}
                <svg
                  className="absolute inset-0 w-full h-full select-none"
                  viewBox="0 0 1000 1000"
                  preserveAspectRatio="none"
                >
                  {/* Render all finished polygons */}
                  {configuredZones.map((m, zIdx) => {
                    const color = getZoneColor(zIdx);
                    const isSelected = String(m.zoneId) === String(selectedZoneId);
                    const pointsStr = formatSvgPoints(m.polygon, 1000);
                    const centroid = computePolygonCentroid(m.polygon);

                    return (
                      <g key={m.zoneId}>
                        {/* Polygon Body */}
                        <polygon
                          points={pointsStr}
                          fill={isSelected ? color.fillActive : color.fill}
                          stroke={color.stroke}
                          strokeWidth={isSelected ? 4 : 2.5}
                          strokeDasharray={isSelected ? 'none' : '6 3'}
                          className="cursor-pointer transition-colors"
                          onClick={(e) => {
                            e.stopPropagation();
                            if (!isDrawing) setSelectedZoneId(m.zoneId);
                          }}
                        />

                        {/* Zone Name Label at Centroid */}
                        <g
                          transform={`translate(${centroid.x * 1000}, ${centroid.y * 1000})`}
                          className="pointer-events-none select-none"
                        >
                          <rect
                            x="-65"
                            y="-14"
                            width="130"
                            height="28"
                            rx="8"
                            fill="#020617"
                            fillOpacity="0.85"
                            stroke={color.stroke}
                            strokeWidth="1.5"
                          />
                          <text
                            x="0"
                            y="4"
                            textAnchor="middle"
                            fill="#ffffff"
                            fontSize="16"
                            fontWeight="bold"
                            className="font-sans"
                          >
                            {m.zoneName || `Zone ${m.zoneId}`}
                          </text>
                        </g>

                        {/* Draggable Vertex Handles for Selected Polygon (Admin only) */}
                        {isSelected &&
                          isAdmin &&
                          !isDrawing &&
                          m.polygon.map((pt, vIdx) => (
                            <circle
                              key={vIdx}
                              cx={pt.x * 1000}
                              cy={pt.y * 1000}
                              r={10}
                              fill="#ffffff"
                              stroke={color.stroke}
                              strokeWidth={3}
                              className="cursor-move hover:scale-125 transition-transform"
                              onPointerDown={(e) => handleVertexMouseDown(e, m.zoneId, vIdx)}
                            >
                              <title>{`Vertex ${vIdx + 1}: (${pt.x.toFixed(3)}, ${pt.y.toFixed(3)})`}</title>
                            </circle>
                          ))}
                      </g>
                    );
                  })}

                  {/* Render Polygon Currently Being Drawn */}
                  {isDrawing && drawingPoints.length > 0 && (
                    <g>
                      {/* Existing completed edges of draft */}
                      {drawingPoints.length >= 2 && (
                        <polyline
                          points={formatSvgPoints(drawingPoints, 1000)}
                          fill="none"
                          stroke="#38bdf8"
                          strokeWidth="3"
                          strokeDasharray="6 4"
                        />
                      )}

                      {/* Line to current cursor */}
                      {currentCursorNorm && drawingPoints.length > 0 && (
                        <line
                          x1={drawingPoints[drawingPoints.length - 1].x * 1000}
                          y1={drawingPoints[drawingPoints.length - 1].y * 1000}
                          x2={currentCursorNorm.x * 1000}
                          y2={currentCursorNorm.y * 1000}
                          stroke="#38bdf8"
                          strokeWidth="2"
                          strokeDasharray="4 4"
                        />
                      )}

                      {/* Vertices of draft polygon */}
                      {drawingPoints.map((pt, i) => (
                        <g key={i}>
                          <circle
                            cx={pt.x * 1000}
                            cy={pt.y * 1000}
                            r={i === 0 ? 12 : 8}
                            fill={i === 0 ? '#10b981' : '#38bdf8'}
                            stroke="#ffffff"
                            strokeWidth={2.5}
                          />
                          <text
                            x={pt.x * 1000}
                            y={pt.y * 1000 - 12}
                            textAnchor="middle"
                            fill="#ffffff"
                            fontSize="14"
                            fontWeight="bold"
                          >
                            {i + 1}
                          </text>
                        </g>
                      ))}
                    </g>
                  )}
                </svg>
              </div>
            </div>

            {/* Bottom In-Canvas Controls & Drawing Feedback */}
            <div className="mt-3 p-3 rounded-2xl bg-slate-900 border border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
              <div className="flex items-center gap-2">
                {isDrawing ? (
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
                    <span className="font-bold text-white">Drawing Zone Boundary:</span>
                    <span className="text-sky-400 font-semibold">
                      {drawingPoints.length} {drawingPoints.length === 1 ? 'vertex' : 'vertices'} placed
                    </span>
                    <span className="text-slate-400">
                      {drawingPoints.length < 3
                        ? `(Need at least ${3 - drawingPoints.length} more)`
                        : '(Ready to close - click Complete or first vertex)'}
                    </span>
                  </div>
                ) : selectedMapping ? (
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-white">Selected Zone:</span>
                    <span className="text-sky-400 font-bold">{selectedMapping.zoneName}</span>
                    <span className="text-slate-400">({selectedMapping.polygon?.length || 0} vertices)</span>
                    <span className="text-slate-500 font-mono text-[11px] ml-2">
                      Priority: {selectedMapping.priority ?? 1}
                    </span>
                  </div>
                ) : (
                  <div className="text-slate-400 flex items-center gap-1.5">
                    <Info className="w-4 h-4 text-sky-400 flex-shrink-0" />
                    <span>
                      {configuredZones.length === 0
                        ? 'No safety zone boundaries configured for this camera yet. Select a zone from the right panel to begin calibration.'
                        : 'Select a zone from the sidebar or click a polygon on the canvas to inspect or adjust its vertices.'}
                    </span>
                  </div>
                )}
              </div>

              {/* Drawing Action Buttons */}
              {isDrawing && (
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={undoLastPoint}
                    disabled={drawingPoints.length === 0}
                    className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-300 font-semibold transition"
                  >
                    <Undo2 className="w-3.5 h-3.5" />
                    <span>Undo Point</span>
                  </button>

                  <button
                    type="button"
                    onClick={cancelDrawing}
                    className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-rose-300 font-semibold transition"
                  >
                    Cancel
                  </button>

                  <button
                    type="button"
                    onClick={completeDrawing}
                    disabled={drawingPoints.length < 3}
                    className="flex items-center gap-1.5 px-4 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white font-bold shadow-md shadow-emerald-600/30 transition"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Complete Polygon</span>
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Right Sidebar: Factory Zones & Selected Zone Configuration (1 Column) */}
          <div className="p-5 border-t lg:border-t-0 lg:border-l border-slate-800 bg-slate-950 flex flex-col justify-between overflow-y-auto space-y-4">
            <div className="space-y-4">
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-1.5">
                  <Layers className="w-4 h-4 text-sky-400" />
                  <span>Factory Safety Zones</span>
                </h3>
                <p className="text-[11px] text-slate-500">
                  Select a zone to draw a polygon or adjust its spatial parameters
                </p>
              </div>

              {/* Zones List */}
              <div className="space-y-2 max-h-[38vh] overflow-y-auto pr-1">
                {availableZones.map((z, idx) => {
                  const zid = String(z._id || z.id);
                  const configured = configuredZones.find((m) => String(m.zoneId) === zid);
                  const isSelected = selectedZoneId === zid;
                  const isCurrentlyDrawing = isDrawing && drawingTargetZoneId === zid;
                  const color = getZoneColor(idx);

                  return (
                    <div
                      key={zid}
                      onClick={() => {
                        if (!isDrawing) setSelectedZoneId(zid);
                      }}
                      className={`p-3 rounded-2xl border transition cursor-pointer flex flex-col justify-between ${
                        isSelected
                          ? 'bg-slate-900 border-sky-500 shadow-md ring-1 ring-sky-500/30'
                          : configured
                          ? 'bg-slate-950 border-slate-800 hover:border-slate-700'
                          : 'bg-slate-950/40 border-dashed border-slate-800 hover:border-slate-700'
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-2">
                          <span
                            className="w-3 h-3 rounded-full flex-shrink-0"
                            style={{ backgroundColor: color.stroke }}
                          />
                          <div>
                            <div className="font-bold text-white text-xs leading-tight">{z.name}</div>
                            <span className="text-[10px] text-slate-500 font-mono">{z.code || zid}</span>
                          </div>
                        </div>

                        {configured ? (
                          <span className="px-2 py-0.5 rounded-full bg-emerald-950 border border-emerald-800 text-emerald-400 text-[10px] font-bold">
                            Configured ({configured.polygon?.length} pts)
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded-full bg-slate-900 border border-slate-800 text-slate-500 text-[10px]">
                            Unmapped
                          </span>
                        )}
                      </div>

                      {/* Required PPE badges for this zone */}
                      {Array.isArray(z.requiredPPE) && z.requiredPPE.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {z.requiredPPE.map((ppe) => (
                            <span
                              key={ppe}
                              className="px-1.5 py-0.5 rounded bg-slate-900 text-slate-300 text-[9px] font-medium uppercase"
                            >
                              {ppe}
                            </span>
                          ))}
                        </div>
                      )}

                      {/* Action buttons on card */}
                      {isAdmin && (
                        <div className="mt-2 pt-2 border-t border-slate-800/80 flex items-center justify-between">
                          {!configured ? (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                startDrawing(zid);
                              }}
                              disabled={isDrawing}
                              className="text-[11px] font-bold text-sky-400 hover:text-sky-300 flex items-center gap-1 transition"
                            >
                              <Plus className="w-3 h-3" />
                              <span>{isCurrentlyDrawing ? 'Drawing Now...' : 'Draw Polygon'}</span>
                            </button>
                          ) : (
                            <div className="w-full flex items-center justify-between">
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  startDrawing(zid);
                                }}
                                disabled={isDrawing}
                                className="text-[10px] font-semibold text-slate-400 hover:text-sky-400 transition"
                              >
                                Redraw
                              </button>
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDeletePolygon(zid);
                                }}
                                className="text-[10px] font-semibold text-rose-400 hover:text-rose-300 transition"
                              >
                                Delete
                              </button>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* Selected Polygon Properties Panel */}
              {selectedMapping && (
                <div className="p-3.5 rounded-2xl bg-slate-900 border border-slate-800 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1">
                      <Sliders className="w-3.5 h-3.5 text-sky-400" />
                      Polygon Settings
                    </span>
                    {isAdmin && (
                      <button
                        type="button"
                        onClick={() => handleDeletePolygon(selectedMapping.zoneId)}
                        className="text-rose-400 hover:text-rose-300 text-xs font-semibold flex items-center gap-1 transition"
                        title="Delete this polygon"
                      >
                        <Trash2 className="w-3 h-3" />
                        <span>Delete</span>
                      </button>
                    )}
                  </div>

                  <div>
                    <label className="block text-[11px] text-slate-400 font-medium mb-1">
                      Resolution Priority (Overlapping Zones):
                    </label>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        min="0"
                        max="99"
                        disabled={!isAdmin}
                        value={selectedMapping.priority ?? 1}
                        onChange={(e) => handlePriorityChange(selectedMapping.zoneId, e.target.value)}
                        className="w-20 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500 font-mono disabled:opacity-50"
                      />
                      <span className="text-[10px] text-slate-500 leading-tight">
                        Higher priority wins when a worker anchor lands in overlapping polygons.
                      </span>
                    </div>
                  </div>

                  <div className="text-[11px] text-slate-400 pt-2 border-t border-slate-800 flex justify-between">
                    <span>Vertices:</span>
                    <span className="text-white font-mono font-bold">{selectedMapping.polygon?.length}</span>
                  </div>
                </div>
              )}
            </div>

            {/* Bottom Actions: Reload & Save */}
            <div className="pt-4 border-t border-slate-800 space-y-2 flex-shrink-0">
              {isAdmin ? (
                <>
                  <button
                    type="button"
                    onClick={handleSave}
                    disabled={saving || isDrawing}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-white text-xs font-bold shadow-lg shadow-sky-600/30 transition"
                  >
                    <Save className="w-4 h-4" />
                    <span>{saving ? 'Saving Polygons to Backend...' : 'Save Zone Polygons'}</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => loadCameraPolygons(activeCameraId)}
                    disabled={loading || saving}
                    className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-slate-200 text-xs font-semibold transition"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    <span>Reload Saved Polygons</span>
                  </button>
                </>
              ) : (
                <div className="text-center p-3 rounded-xl bg-slate-900 border border-slate-800 text-slate-400 text-xs">
                  Read-only view for Zone Supervisors.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
