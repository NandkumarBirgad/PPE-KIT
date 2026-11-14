import React, { useState, useRef, useEffect } from 'react';
import {
  Upload,
  Play,
  Pause,
  RotateCcw,
  SkipForward,
  SkipBack,
  Film,
  Camera,
  Layers,
  AlertTriangle,
  CheckCircle2,
  Clock,
  ShieldAlert,
  ShieldCheck,
  ExternalLink,
  ChevronRight,
  Sliders,
  X,
  FileVideo,
  Eye,
  Info
} from 'lucide-react';
import { Link } from 'react-router-dom';
import api, { AI_BASE_URL } from '../services/api';
import CameraPolygonModal from './CameraPolygonModal';
import { getZoneColor, formatSvgPoints, computePolygonCentroid } from '../services/cameraPolygonService';

export default function UploadedVideoInspector({
  allCameras = [],
  availableZones = [],
  onCameraPolygonsUpdated
}) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [videoPreviewUrl, setVideoPreviewUrl] = useState(null);
  const [extractedFrameUrl, setExtractedFrameUrl] = useState(null);
  const [videoDuration, setVideoDuration] = useState(0);

  // Camera profile association
  const [selectedCameraId, setSelectedCameraId] = useState(''); // '' means unzoned mode
  const [showPolygonModal, setShowPolygonModal] = useState(false);

  // Processing state
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingError, setProcessingError] = useState('');
  const [inspectionResult, setInspectionResult] = useState(null);

  // Playback state for processed frames
  const [currentFrameIdx, setCurrentFrameIdx] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(800); // ms per frame
  const [showZoneBoundaries, setShowZoneBoundaries] = useState(true);

  const fileInputRef = useRef(null);
  const playbackTimerRef = useRef(null);

  // Selected camera profile object
  const activeCamera = allCameras.find((c) => String(c._id) === String(selectedCameraId)) || null;
  const hasPolygons = Boolean(activeCamera && Array.isArray(activeCamera.zones) && activeCamera.zones.length > 0);

  // Handle video file selection & representative frame extraction
  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith('video/')) {
      setProcessingError('Please select a valid video file (.mp4, .webm, .mov, etc.)');
      return;
    }

    setSelectedFile(file);
    setProcessingError('');
    setInspectionResult(null);
    setCurrentFrameIdx(0);
    setIsPlaying(false);

    const blobUrl = URL.createObjectURL(file);
    setVideoPreviewUrl(blobUrl);

    // Extract representative frame using an offscreen video element
    const tempVideo = document.createElement('video');
    tempVideo.preload = 'metadata';
    tempVideo.src = blobUrl;
    tempVideo.muted = true;
    tempVideo.playsInline = true;

    tempVideo.onloadeddata = () => {
      setVideoDuration(tempVideo.duration || 0);
      tempVideo.currentTime = Math.min(1.0, (tempVideo.duration || 2) / 2);
    };

    tempVideo.onseeked = () => {
      try {
        const canvas = document.createElement('canvas');
        canvas.width = tempVideo.videoWidth || 1280;
        canvas.height = tempVideo.videoHeight || 720;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(tempVideo, 0, 0, canvas.width, canvas.height);
        const frameDataUrl = canvas.toDataURL('image/jpeg', 0.9);
        setExtractedFrameUrl(frameDataUrl);
      } catch (err) {
        console.warn('Could not extract video frame on canvas:', err);
      }
    };
  };

  // Run video inspection processing
  const handleStartInspection = async () => {
    if (!selectedFile) {
      setProcessingError('Please select a video file to inspect.');
      return;
    }

    setIsProcessing(true);
    setProcessingError('');
    setInspectionResult(null);
    setCurrentFrameIdx(0);
    setIsPlaying(false);

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      if (selectedCameraId) {
        formData.append('cameraId', selectedCameraId);
      }
      formData.append('confidence_threshold', '0.35');
      formData.append('confirmation_duration_sec', '3.0');
      formData.append('sample_interval_sec', '0.8');
      formData.append('max_frames', '60');

      const res = await api.post('/detect-video', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 120000
      });

      const data = res.data;
      setInspectionResult(data);
      setCurrentFrameIdx(0);

      // Auto-start playback of processed frames
      if (Array.isArray(data.frame_breakdown) && data.frame_breakdown.length > 0) {
        setIsPlaying(true);
      }
    } catch (err) {
      console.error('Video processing failed:', err);
      setProcessingError(err.response?.data?.message || err.message || 'Video inspection failed.');
    } finally {
      setIsProcessing(false);
    }
  };

  // Frame playback timer loop
  useEffect(() => {
    if (isPlaying && inspectionResult?.frame_breakdown?.length) {
      playbackTimerRef.current = setInterval(() => {
        setCurrentFrameIdx((prev) => {
          if (prev >= inspectionResult.frame_breakdown.length - 1) {
            setIsPlaying(false);
            return prev;
          }
          return prev + 1;
        });
      }, playbackSpeed);
    } else {
      if (playbackTimerRef.current) clearInterval(playbackTimerRef.current);
    }
    return () => {
      if (playbackTimerRef.current) clearInterval(playbackTimerRef.current);
    };
  }, [isPlaying, inspectionResult, playbackSpeed]);

  const currentFrame = inspectionResult?.frame_breakdown?.[currentFrameIdx] || null;
  const activeCameraZones = activeCamera?.zones || inspectionResult?.camera_profile?.zones || [];

  return (
    <div className="space-y-6">
      {/* 1. Upload & Camera Profile Association Card */}
      <div className="bg-slate-900 border border-slate-800 rounded-3xl p-5 lg:p-6 shadow-xl">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 border-b border-slate-800 pb-5">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="w-10 h-10 rounded-2xl bg-sky-950 border border-sky-800 text-sky-400 flex items-center justify-center font-bold shadow-lg shadow-sky-950/40">
                <Film className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-white tracking-tight">Prerecorded Factory Video Demonstration</h2>
                <p className="text-xs text-slate-400">
                  Inspect recorded CCTV footage through the spatial zone resolver, anonymous tracking, and temporal compliance engine
                </p>
              </div>
            </div>
          </div>

          {/* Quick File Select Button */}
          <div className="flex items-center gap-2.5">
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept="video/*"
              className="hidden"
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition"
            >
              <Upload className="w-4 h-4 text-sky-400" />
              <span>{selectedFile ? 'Change Video File' : 'Select Factory Video'}</span>
            </button>
          </div>
        </div>

        {/* Configuration Row: Video Info & Explicit Camera Profile */}
        <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Selected File Details */}
          <div className="p-4 rounded-2xl bg-slate-950 border border-slate-800 flex flex-col justify-between">
            <div>
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                Selected Video File
              </span>
              {selectedFile ? (
                <div className="flex items-center gap-2 text-white font-semibold text-xs truncate">
                  <FileVideo className="w-4 h-4 text-sky-400 flex-shrink-0" />
                  <span className="truncate">{selectedFile.name}</span>
                  <span className="text-[10px] text-slate-400 font-mono flex-shrink-0">
                    ({(selectedFile.size / (1024 * 1024)).toFixed(1)} MB
                    {videoDuration > 0 ? ` • ${Math.round(videoDuration)}s` : ''})
                  </span>
                </div>
              ) : (
                <p className="text-xs text-slate-500 italic">No video selected. Click "Select Factory Video" above.</p>
              )}
            </div>

            {selectedFile && extractedFrameUrl && (
              <div className="mt-3 flex items-center justify-between pt-2 border-t border-slate-800/80 text-xs">
                <span className="text-[11px] text-emerald-400 font-medium flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Frame extracted for calibration
                </span>
                {activeCamera && (
                  <button
                    type="button"
                    onClick={() => setShowPolygonModal(true)}
                    className="text-[11px] font-bold text-sky-400 hover:text-sky-300 flex items-center gap-1 transition"
                  >
                    <Layers className="w-3.5 h-3.5" />
                    <span>Calibrate Zones on this Frame</span>
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Camera Profile Association Dropdown */}
          <div className="p-4 rounded-2xl bg-slate-950 border border-slate-800 flex flex-col justify-between">
            <div>
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                Associated Camera Profile & Zones
              </span>
              <select
                value={selectedCameraId}
                onChange={(e) => setSelectedCameraId(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white font-semibold focus:outline-none focus:ring-2 focus:ring-sky-500 cursor-pointer"
              >
                <option value="">Unzoned Mode (Facility-Wide Inspection • No Polygons)</option>
                {allCameras.map((c) => (
                  <option key={c._id} value={c._id}>
                    {c.name} ({Array.isArray(c.zones) && c.zones.length > 0 ? `${c.zones.length} Safety Zones` : 'Camera Zone Fallback'})
                  </option>
                ))}
              </select>
            </div>

            {/* Profile Status Badge */}
            <div className="mt-3 pt-2 border-t border-slate-800/80 flex items-center justify-between text-xs">
              {activeCamera ? (
                <div className="flex items-center gap-2 text-sky-400 text-[11px] font-semibold">
                  <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase border ${
                    activeCamera.status === 'ONLINE'
                      ? 'bg-emerald-950 text-emerald-400 border-emerald-800'
                      : activeCamera.status === 'COMPLETED'
                      ? 'bg-sky-950 text-sky-300 border-sky-800'
                      : activeCamera.status === 'WARNING'
                      ? 'bg-amber-950 text-amber-300 border-amber-800'
                      : 'bg-rose-950 text-rose-400 border-rose-800'
                  }`}>
                    {activeCamera.status || 'ONLINE'}
                  </span>
                  <span>
                    {hasPolygons
                      ? `${activeCamera.zones.length} spatial safety zones configured`
                      : 'Camera-level default zone (legacy mode)'}
                  </span>
                </div>
              ) : (
                <div className="text-slate-500 text-[11px]">
                  Unzoned: Workers evaluated against general PPE rules.
                </div>
              )}

              {activeCamera && (
                <button
                  type="button"
                  onClick={() => setShowPolygonModal(true)}
                  className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-[10px] font-semibold transition"
                >
                  Inspect Polygons
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Start Inspection Action Button */}
        <div className="mt-4 flex items-center justify-between">
          <div className="text-xs text-slate-400">
            {isProcessing && (
              <span className="flex items-center gap-2 text-sky-400 font-semibold animate-pulse">
                <span className="w-2 h-2 rounded-full bg-sky-400 animate-ping"></span>
                Processing frames through YOLOv8, spatial resolver, and temporal state machine...
              </span>
            )}
            {processingError && (
              <span className="flex items-center gap-1.5 text-rose-400 font-semibold">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                {processingError}
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={handleStartInspection}
            disabled={!selectedFile || isProcessing}
            className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-white text-xs font-bold shadow-lg shadow-sky-600/30 transition"
          >
            {isProcessing ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                <span>Inspecting Video...</span>
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                <span>Start Video Inspection</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* 2. Inspection Player & Live Annotated Frame Playback */}
      {inspectionResult && (
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-5 lg:p-6 shadow-2xl space-y-5 animate-in fade-in">
          {/* Summary Banner */}
          <div
            className={`p-4 rounded-2xl border flex flex-col md:flex-row md:items-center md:justify-between gap-3 ${
              inspectionResult.overall_compliance_status === 'COMPLIANT'
                ? 'bg-emerald-950/60 border-emerald-800 text-emerald-200'
                : 'bg-rose-950/60 border-rose-800 text-rose-200'
            }`}
          >
            <div className="flex items-center gap-3">
              {inspectionResult.overall_compliance_status === 'COMPLIANT' ? (
                <ShieldCheck className="w-8 h-8 text-emerald-400 flex-shrink-0" />
              ) : (
                <ShieldAlert className="w-8 h-8 text-rose-400 flex-shrink-0" />
              )}
              <div>
                <h3 className="font-bold text-sm lg:text-base leading-tight">
                  {inspectionResult.overall_compliance_status === 'COMPLIANT'
                    ? 'Inspection Complete: All Workers Fully Compliant'
                    : 'Inspection Complete: Safety Violations Confirmed'}
                </h3>
                <p className="text-xs opacity-85 mt-0.5">
                  Processed {inspectionResult.total_frames_processed} chronological frames. Found{' '}
                  <strong>{inspectionResult.total_violations_found}</strong> confirmed violation episode(s) and{' '}
                  <strong>{inspectionResult.total_resolutions_found}</strong> automatic resolution(s).
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Link
                to="/admin/violations"
                className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold border border-slate-700 flex items-center gap-1.5 transition shadow"
              >
                <span>View Violations Log</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>

          {/* Main Video Viewport Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            {/* Left 2 Cols: Annotated Frame Screen */}
            <div className="lg:col-span-2 space-y-3">
              <div className="relative aspect-video rounded-2xl bg-slate-950 border-2 border-slate-800 overflow-hidden shadow-2xl flex items-center justify-center">
                {currentFrame?.annotated_image ? (
                  <img
                    src={currentFrame.annotated_image}
                    alt={`Frame ${currentFrame.frame_idx}`}
                    className="w-full h-full object-contain select-none"
                  />
                ) : (
                  <div className="text-slate-500 text-xs flex flex-col items-center gap-2">
                    <Film className="w-8 h-8 opacity-40" />
                    <span>No frame available</span>
                  </div>
                )}

                {/* Zone Boundaries SVG Overlay */}
                {showZoneBoundaries && activeCameraZones.length > 0 && (
                  <svg
                    className="absolute inset-0 w-full h-full pointer-events-none select-none z-10"
                    viewBox="0 0 1000 1000"
                    preserveAspectRatio="none"
                  >
                    {activeCameraZones.map((m, zIdx) => {
                      const color = getZoneColor(zIdx);
                      const pointsStr = formatSvgPoints(m.polygon, 1000);
                      const centroid = computePolygonCentroid(m.polygon);
                      return (
                        <g key={m.zoneId || zIdx}>
                          <polygon
                            points={pointsStr}
                            fill={color.fill}
                            stroke={color.stroke}
                            strokeWidth="3"
                            strokeDasharray="6 3"
                          />
                          <g transform={`translate(${centroid.x * 1000}, ${centroid.y * 1000})`}>
                            <rect
                              x="-60"
                              y="-13"
                              width="120"
                              height="26"
                              rx="6"
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
                              fontSize="14"
                              fontWeight="bold"
                            >
                              {m.zoneName || `Zone ${m.zoneId}`}
                            </text>
                          </g>
                        </g>
                      );
                    })}
                  </svg>
                )}
              </div>

              {/* Player Controls & Scrubber */}
              <div className="p-3.5 rounded-2xl bg-slate-950 border border-slate-800 flex flex-col gap-2.5">
                {/* Timeline Scrubber */}
                <div className="flex items-center gap-3">
                  <span className="text-[11px] text-slate-400 font-mono w-16">
                    {currentFrame ? `${currentFrame.timestamp_sec.toFixed(1)}s` : '0.0s'}
                  </span>

                  <input
                    type="range"
                    min={0}
                    max={Math.max(0, (inspectionResult.frame_breakdown?.length || 1) - 1)}
                    value={currentFrameIdx}
                    onChange={(e) => {
                      setIsPlaying(false);
                      setCurrentFrameIdx(Number(e.target.value));
                    }}
                    className="flex-1 accent-sky-500 cursor-pointer h-1.5 bg-slate-800 rounded-lg"
                  />

                  <span className="text-[11px] text-slate-400 font-mono w-24 text-right">
                    Frame {currentFrameIdx + 1} / {inspectionResult.frame_breakdown?.length}
                  </span>
                </div>

                {/* Play / Step Buttons & Options */}
                <div className="flex items-center justify-between pt-1">
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setIsPlaying(false);
                        setCurrentFrameIdx((prev) => Math.max(0, prev - 1));
                      }}
                      className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 transition"
                      title="Step Backward 1 Frame"
                    >
                      <SkipBack className="w-4 h-4" />
                    </button>

                    <button
                      type="button"
                      onClick={() => setIsPlaying(!isPlaying)}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-bold shadow-md shadow-sky-600/30 transition"
                    >
                      {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                      <span>{isPlaying ? 'Pause' : 'Play'}</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        setIsPlaying(false);
                        setCurrentFrameIdx((prev) =>
                          Math.min((inspectionResult.frame_breakdown?.length || 1) - 1, prev + 1)
                        );
                      }}
                      className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 transition"
                      title="Step Forward 1 Frame"
                    >
                      <SkipForward className="w-4 h-4" />
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        setIsPlaying(false);
                        setCurrentFrameIdx(0);
                      }}
                      className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-white transition"
                      title="Rewind to Beginning"
                    >
                      <RotateCcw className="w-4 h-4" />
                    </button>
                  </div>

                  <div className="flex items-center gap-3">
                    {/* Speed Selector */}
                    <div className="flex items-center gap-1 text-[11px] text-slate-400">
                      <span>Speed:</span>
                      <button
                        onClick={() => setPlaybackSpeed(800)}
                        className={`px-2 py-0.5 rounded ${playbackSpeed === 800 ? 'bg-sky-600 text-white font-bold' : 'bg-slate-800'}`}
                      >
                        1x
                      </button>
                      <button
                        onClick={() => setPlaybackSpeed(400)}
                        className={`px-2 py-0.5 rounded ${playbackSpeed === 400 ? 'bg-sky-600 text-white font-bold' : 'bg-slate-800'}`}
                      >
                        2x
                      </button>
                    </div>

                    {/* Zone Overlay Toggle */}
                    {activeCameraZones.length > 0 && (
                      <button
                        type="button"
                        onClick={() => setShowZoneBoundaries(!showZoneBoundaries)}
                        className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold flex items-center gap-1 border transition ${
                          showZoneBoundaries
                            ? 'bg-sky-950/60 border-sky-700 text-sky-300'
                            : 'bg-slate-900 border-slate-800 text-slate-400'
                        }`}
                      >
                        <Layers className="w-3.5 h-3.5 text-sky-400" />
                        <span>{showZoneBoundaries ? 'Zones On' : 'Zones Off'}</span>
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Right 1 Col: Current Frame Inspector & Persisted Incidents */}
            <div className="space-y-4 flex flex-col justify-between">
              {/* Current Frame Status Card */}
              <div className="p-4 rounded-2xl bg-slate-950 border border-slate-800 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                    Current Frame Details
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                      currentFrame?.compliance_status === 'COMPLIANT'
                        ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                        : currentFrame?.compliance_status === 'VIOLATION'
                        ? 'bg-rose-950 text-rose-400 border border-rose-800'
                        : 'bg-amber-950 text-amber-400 border border-amber-800'
                    }`}
                  >
                    {currentFrame?.compliance_status || 'UNCERTAIN'}
                  </span>
                </div>

                {/* Workers in this frame */}
                <div className="space-y-2">
                  <span className="text-[11px] font-semibold text-slate-300 block">
                    Workers Present ({currentFrame?.persons?.length || 0}):
                  </span>
                  {currentFrame?.persons?.length === 0 ? (
                    <p className="text-xs text-slate-500 italic">No workers in frame.</p>
                  ) : (
                    <div className="space-y-1.5 max-h-44 overflow-y-auto pr-1">
                      {currentFrame?.persons?.map((p, idx) => (
                        <div
                          key={p.track_id || idx}
                          className="p-2.5 rounded-xl bg-slate-900 border border-slate-800 text-xs flex items-center justify-between"
                        >
                          <div>
                            <div className="font-bold text-white flex items-center gap-1.5">
                              <span>{p.worker_id}</span>
                              <span className="text-[10px] text-slate-400 font-mono font-normal">
                                (Track #{p.track_id})
                              </span>
                            </div>
                            <span className="text-[10px] text-slate-400 block mt-0.5">
                              Zone: {p.zone_name || (p.zone_id ? `Zone ${p.zone_id}` : 'Unassigned / Neutral')}
                            </span>
                          </div>

                          <div className="text-right">
                            {p.compliant ? (
                              <span className="text-[10px] font-bold text-emerald-400 bg-emerald-950 px-2 py-0.5 rounded border border-emerald-800">
                                COMPLIANT
                              </span>
                            ) : p.uncertain ? (
                              <span className="text-[10px] font-bold text-amber-400 bg-amber-950 px-2 py-0.5 rounded border border-amber-800">
                                {p.uncertain_reason || 'UNCERTAIN'}
                              </span>
                            ) : (
                              <span className="text-[10px] font-bold text-rose-400 bg-rose-950 px-2 py-0.5 rounded border border-rose-800">
                                MISSING {p.missing_ppe?.join(', ')?.toUpperCase()}
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Persisted Incidents Timeline List */}
              <div className="p-4 rounded-2xl bg-slate-950 border border-slate-800 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                    <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
                    <span>Persisted Incidents ({inspectionResult.persisted_incidents?.length || 0})</span>
                  </span>
                  <Link
                    to="/admin/violations"
                    className="text-[11px] text-sky-400 hover:text-sky-300 font-semibold"
                  >
                    View All
                  </Link>
                </div>

                <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                  {inspectionResult.persisted_incidents?.length === 0 ? (
                    <div className="text-center py-4 text-xs text-slate-500">
                      No violations confirmed during this inspection session.
                    </div>
                  ) : (
                    inspectionResult.persisted_incidents?.map((inc, i) => (
                      <div
                        key={inc.episode_id || i}
                        className="p-2.5 rounded-xl bg-slate-900 border border-slate-800 text-xs space-y-1"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-white text-xs">{inc.worker_id}</span>
                          <span className="px-1.5 py-0.5 rounded bg-rose-950 text-rose-400 text-[9px] font-bold border border-rose-800 uppercase">
                            OPEN INCIDENT
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-400">
                          Missing: <strong className="text-rose-300">{inc.missingPPE?.join(', ')}</strong> in{' '}
                          {inc.zoneName || 'Monitored Zone'}
                        </div>
                        <div className="text-[10px] text-slate-500 font-mono flex items-center justify-between pt-1 border-t border-slate-800/80">
                          <span>Camera: {inc.cameraName || inc.cameraId}</span>
                          <span>t = {inc.processingMetadata?.video_timestamp_sec ?? 0}s</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 3. Reused Camera Polygon Calibration Modal */}
      {showPolygonModal && (
        <CameraPolygonModal
          camera={activeCamera || allCameras[0]}
          allCameras={allCameras}
          availableZones={availableZones}
          initialReferenceImageUrl={extractedFrameUrl}
          onClose={() => setShowPolygonModal(false)}
          onSaved={(updatedCam) => {
            if (onCameraPolygonsUpdated) onCameraPolygonsUpdated(updatedCam);
          }}
        />
      )}
    </div>
  );
}
