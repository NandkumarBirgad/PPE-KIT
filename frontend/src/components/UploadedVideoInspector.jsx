import React, { useState, useRef, useEffect, useMemo } from 'react';
import {
  Upload,
  Play,
  Pause,
  RotateCcw,
  SkipForward,
  SkipBack,
  Film,
  Layers,
  AlertTriangle,
  CheckCircle2,
  ShieldAlert,
  ShieldCheck,
  ChevronRight,
  FileVideo,
  XCircle,
  Activity,
  Clock
} from 'lucide-react';
import { Link } from 'react-router-dom';
import api, { AI_BASE_URL } from '../services/api';
import CameraPolygonModal from './CameraPolygonModal';
import { getZoneColor, computePolygonCentroid } from '../services/cameraPolygonService';
import {
  findNearestFrame,
  formatVideoTime,
  getComplianceBadgeStyle,
  getPpeBadgeStyle,
  isPlaybackAheadOfAnalysis
} from '../services/videoOverlayService';
import { consumeSseStream } from '../services/sseStreamService';

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

  // Progressive Streaming State
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingStatus, setProcessingStatus] = useState('IDLE'); // 'IDLE', 'UPLOADING', 'ANALYZING', 'COMPLETED', 'CANCELLED', 'FAILED'
  const [analyzingSubStatus, setAnalyzingSubStatus] = useState('');
  const [processingProgressPct, setProcessingProgressPct] = useState(0);
  const [latestAnalyzedTime, setLatestAnalyzedTime] = useState(0);
  const [processingFps, setProcessingFps] = useState(null);
  const [processingError, setProcessingError] = useState('');

  // Progressive Data Collections
  const [frameBreakdown, setFrameBreakdown] = useState([]);
  const [persistedIncidents, setPersistedIncidents] = useState([]);
  const [streamMetadata, setStreamMetadata] = useState(null);
  const [completionSummary, setCompletionSummary] = useState(null);

  // Native Video Player State
  const videoRef = useRef(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [videoPlaying, setVideoPlaying] = useState(false);
  const [videoSpeed, setVideoSpeed] = useState(1.0);
  const [videoDimensions, setVideoDimensions] = useState({ width: 1920, height: 1080 });

  // Overlays
  const [showZoneBoundaries, setShowZoneBoundaries] = useState(true);

  const fileInputRef = useRef(null);
  const abortControllerRef = useRef(null);

  // Cleanup in-flight stream on component unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

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

    // Abort any prior in-flight inspection
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    setSelectedFile(file);
    setProcessingError('');
    setIsProcessing(false);
    setProcessingStatus('IDLE');
    setAnalyzingSubStatus('');
    setProcessingProgressPct(0);
    setLatestAnalyzedTime(0);
    setProcessingFps(null);
    setFrameBreakdown([]);
    setPersistedIncidents([]);
    setStreamMetadata(null);
    setCompletionSummary(null);
    setCurrentTime(0);
    setVideoPlaying(false);

    if (videoPreviewUrl) {
      URL.revokeObjectURL(videoPreviewUrl);
    }
    const blobUrl = URL.createObjectURL(file);
    setVideoPreviewUrl(blobUrl);

    // Extract representative frame using an offscreen video element
    const tempVideo = document.createElement('video');
    tempVideo.preload = 'metadata';
    tempVideo.src = blobUrl;
    tempVideo.muted = true;
    tempVideo.playsInline = true;

    tempVideo.onloadedmetadata = () => {
      const dur = tempVideo.duration || 0;
      setVideoDuration(dur);
      if (tempVideo.videoWidth && tempVideo.videoHeight) {
        setVideoDimensions({ width: tempVideo.videoWidth, height: tempVideo.videoHeight });
      }
      tempVideo.currentTime = Math.min(1.0, dur / 2);
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

  // Run progressive video inspection via Server-Sent Events (SSE)
  const handleStartInspection = async () => {
    if (!selectedFile) {
      setProcessingError('Please select a video file to inspect.');
      return;
    }

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    // Explicit ANALYZING state immediately
    setIsProcessing(true);
    setProcessingStatus('ANALYZING');
    setAnalyzingSubStatus('Connecting to AI streaming pipeline...');
    setProcessingError('');
    setProcessingProgressPct(0);
    setLatestAnalyzedTime(0);
    setProcessingFps(null);
    setFrameBreakdown([]);
    setPersistedIncidents([]);
    setStreamMetadata(null);
    setCompletionSummary(null);

    // Rewind video playhead to 0:00 and auto-play to synchronize playback with inspection from frame 0
    if (videoRef.current) {
      videoRef.current.currentTime = 0;
      setCurrentTime(0);
      videoRef.current.play().catch(() => {});
    }

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      if (selectedCameraId) {
        formData.append('cameraId', selectedCameraId);
      }
      formData.append('confidence_threshold', '0.35');
      formData.append('confirmation_duration_sec', '3.0');
      formData.append('sample_interval_sec', '0.5');
      formData.append('max_frames', '300');

      const token = localStorage.getItem('ppe_auth_token');
      const headers = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      setAnalyzingSubStatus('Uploading video to inspection pipeline...');

      const response = await fetch(`${AI_BASE_URL}/api/detect-video-stream`, {
        method: 'POST',
        headers,
        body: formData,
        signal: controller.signal
      });

      if (!response.ok) {
        let errMessage = 'Video streaming inspection failed.';
        try {
          const errJson = await response.json();
          errMessage = errJson.message || errMessage;
        } catch (_) {}
        throw new Error(errMessage);
      }

      setAnalyzingSubStatus('Connected. Analyzing video frames progressively...');

      await consumeSseStream(
        response.body,
        ({ event, data }) => {
          if (controller.signal.aborted) return;

          switch (event) {
            case 'init':
              setStreamMetadata(data);
              setProcessingStatus('ANALYZING');
              setAnalyzingSubStatus(`Stream active: ${data.duration_sec?.toFixed(1) || ''}s duration, ${data.fps || 25} FPS (sampling every ${data.sample_interval_sec || 0.8}s)`);
              break;

            case 'frame':
              setFrameBreakdown((prev) => {
                // When first frame arrives, resynchronize playback to 0:00 if initial network upload caused playhead drift
                if (prev.length === 0 && videoRef.current) {
                  if (videoRef.current.currentTime > 0.6) {
                    videoRef.current.currentTime = 0;
                  }
                  if (videoRef.current.paused) {
                    videoRef.current.play().catch(() => {});
                    setVideoPlaying(true);
                  }
                }
                return [...prev, data];
              });
              if (data.timestamp_sec != null) {
                setLatestAnalyzedTime(data.timestamp_sec);
                const fpsText = data.latency_ms ? ` • ${Math.round(1000 / Math.max(data.latency_ms, 1))} FPS (${data.latency_ms}ms)` : '';
                setAnalyzingSubStatus(`Analyzed frame #${data.frame_idx || ''} at ${data.timestamp_sec.toFixed(1)}s (${data.persons_count || data.persons?.length || 0} workers${fpsText})`);
              }
              break;

            case 'incident':
              setPersistedIncidents((prev) => {
                if (prev.some((inc) => inc.episode_id === data.episode_id)) {
                  return prev;
                }
                return [data, ...prev];
              });
              break;

            case 'resolution':
              setPersistedIncidents((prev) =>
                prev.map((inc) =>
                  inc.episode_id === data.episode_id
                    ? { ...inc, status: 'RESOLVED', resolution: data }
                    : inc
                )
              );
              break;

            case 'progress':
              if (data.progress_pct != null) {
                setProcessingProgressPct(data.progress_pct);
              }
              if (data.timestamp_sec != null) {
                setLatestAnalyzedTime(data.timestamp_sec);
              }
              if (data.processing_fps != null) {
                setProcessingFps(data.processing_fps);
              }
              break;

            case 'done':
              setCompletionSummary(data);
              setProcessingStatus('COMPLETED');
              setAnalyzingSubStatus('');
              setIsProcessing(false);
              break;

            case 'error':
              setProcessingError(data.message || 'Stream processing error.');
              setProcessingStatus('FAILED');
              setAnalyzingSubStatus('');
              setIsProcessing(false);
              break;

            default:
              break;
          }
        },
        (streamErr) => {
          if (!controller.signal.aborted) {
            setProcessingError(streamErr.message || 'Stream connection error.');
            setProcessingStatus('FAILED');
            setAnalyzingSubStatus('');
            setIsProcessing(false);
          }
        },
        controller.signal
      );
    } catch (err) {
      if (err.name === 'AbortError' || controller.signal.aborted) {
        setProcessingStatus('CANCELLED');
        setAnalyzingSubStatus('Inspection cancelled by user.');
      } else {
        console.error('Progressive video inspection failed:', err);
        setProcessingError(err.message || 'Video inspection failed.');
        setProcessingStatus('FAILED');
        setAnalyzingSubStatus('');
      }
      setIsProcessing(false);
    }
  };

  const handleCancelInspection = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsProcessing(false);
    setProcessingStatus('CANCELLED');
    setAnalyzingSubStatus('Inspection cancelled by user.');
  };

  // Stale Overlay & Temporal Analysis Front Lag Detection (2.5s tolerance)
  const isStale = useMemo(() => {
    return isPlaybackAheadOfAnalysis(currentTime, latestAnalyzedTime, isProcessing, 2.5);
  }, [currentTime, latestAnalyzedTime, isProcessing]);

  // Synchronize Nearest Active Frame to Current Native Video Time
  const nearestFrame = useMemo(() => {
    if (!frameBreakdown?.length) return null;
    return findNearestFrame(currentTime, frameBreakdown);
  }, [frameBreakdown, currentTime]);

  // Active frame selection: matches nearest frame within 2.0s tolerance of current video time.
  // Never suppresses frames that were legitimately analyzed at or near current video time.
  const activeFrame = useMemo(() => {
    if (!nearestFrame) return null;
    if (nearestFrame._timeDiff > 2.0) {
      return null;
    }
    return nearestFrame;
  }, [nearestFrame]);

  // Native Video Player Controls
  const togglePlayPause = () => {
    if (!videoRef.current) return;
    if (videoPlaying) {
      videoRef.current.pause();
    } else {
      videoRef.current.play().catch(() => {});
    }
  };

  const handleSeek = (newTime) => {
    const clamped = Math.max(0, Math.min(newTime, videoDuration || 0));
    setCurrentTime(clamped);
    if (videoRef.current) {
      videoRef.current.currentTime = clamped;
    }
  };

  const handleSpeedChange = (speed) => {
    setVideoSpeed(speed);
    if (videoRef.current) {
      videoRef.current.playbackRate = speed;
    }
  };

  const handleSeekToIncident = (inc) => {
    const t = inc.processingMetadata?.video_timestamp_sec ?? inc.confirmed_timestamp ?? 0;
    handleSeek(t);
    if (videoRef.current) {
      videoRef.current.pause();
      setVideoPlaying(false);
    }
  };

  // M2.6 Authoritative Inspection Summary Metrics
  const summaryMetrics = useMemo(() => {
    if (!completionSummary && processingStatus !== 'COMPLETED') return null;

    const workerMap = new Map();
    for (const frame of frameBreakdown) {
      for (const p of frame.persons || []) {
        const wid = p.worker_id;
        if (!wid) continue;
        const prev = workerMap.get(wid) || { hasViolation: false, hasUncertain: false, compliantCount: 0 };
        const isVio = Boolean(p.missing_ppe?.length > 0) || (!p.compliant && !p.uncertain && !p.pending_missing_ppe?.length);
        const isUnc = Boolean(p.uncertain || p.pending_missing_ppe?.length > 0);
        if (isVio) prev.hasViolation = true;
        if (isUnc) prev.hasUncertain = true;
        if (p.compliant && !isVio && !isUnc) prev.compliantCount++;
        workerMap.set(wid, prev);
      }
    }

    let violationWorkers = 0;
    let uncertainWorkers = 0;
    let compliantWorkers = 0;

    for (const [, state] of workerMap.entries()) {
      if (state.hasViolation) {
        violationWorkers++;
      } else if (state.hasUncertain) {
        uncertainWorkers++;
      } else if (state.compliantCount > 0) {
        compliantWorkers++;
      }
    }

    const totalWorkers = workerMap.size;
    const detectedCategories = (completionSummary?.overall_detected_classes || [])
      .map((d) => (d.name || d.class || '').toLowerCase())
      .filter((v, i, a) => v && a.indexOf(v) === i);

    return {
      totalWorkers,
      compliantWorkers,
      violationWorkers,
      uncertainWorkers,
      detectedCategories
    };
  }, [completionSummary, processingStatus, frameBreakdown]);

  const activeCameraZones = activeCamera?.zones || streamMetadata?.camera_profile?.zones || [];

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
                    {videoDuration > 0 ? ` • ${Math.round(videoDuration)}s` : ''}
                    {videoDimensions.width > 0 ? ` • ${videoDimensions.width}x${videoDimensions.height}` : ''})
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

        {/* Start / Cancel Inspection Action Button */}
        <div className="mt-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="text-xs text-slate-400">
            {isProcessing && (
              <span className="flex items-center gap-2 text-sky-400 font-semibold animate-pulse">
                <span className="w-2 h-2 rounded-full bg-sky-400 animate-ping"></span>
                <span>{analyzingSubStatus || `AI stream active: ${frameBreakdown.length} frames analyzed...`}</span>
              </span>
            )}
            {processingStatus === 'CANCELLED' && (
              <span className="flex items-center gap-1.5 text-amber-400 font-medium">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                Inspection cancelled. Partial analysis results preserved ({frameBreakdown.length} frames analyzed).
              </span>
            )}
            {processingError && (
              <span className="flex items-center gap-1.5 text-rose-400 font-semibold">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                {processingError}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {isProcessing && (
              <button
                type="button"
                onClick={handleCancelInspection}
                className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-rose-950 hover:bg-rose-900 border border-rose-700 text-rose-300 text-xs font-bold transition shadow"
              >
                <XCircle className="w-4 h-4" />
                <span>Cancel Inspection</span>
              </button>
            )}

            <button
              type="button"
              onClick={handleStartInspection}
              disabled={!selectedFile || isProcessing}
              className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-white text-xs font-bold shadow-lg shadow-sky-600/30 transition"
            >
              {isProcessing ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  <span>Analyzing Stream ({frameBreakdown.length} frames)...</span>
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  <span>{frameBreakdown.length > 0 ? 'Restart Video Inspection' : 'Start Video Inspection'}</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Progressive Processing Progress & Lag HUD Banner */}
      {selectedFile && processingStatus !== 'IDLE' && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-lg space-y-2.5 animate-in fade-in">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between text-xs gap-2">
            <div className="flex items-center gap-2.5">
              <span className={`px-2.5 py-0.5 rounded-lg text-[10px] font-bold uppercase border tracking-wider ${
                processingStatus === 'COMPLETED'
                  ? 'bg-emerald-950 text-emerald-300 border-emerald-700'
                  : processingStatus === 'ANALYZING'
                  ? 'bg-sky-950 text-sky-300 border-sky-600 animate-pulse'
                  : processingStatus === 'CANCELLED'
                  ? 'bg-amber-950 text-amber-300 border-amber-700'
                  : 'bg-rose-950 text-rose-300 border-rose-700'
              }`}>
                {processingStatus}
              </span>
              <span className="font-semibold text-slate-200">
                {processingStatus === 'COMPLETED'
                  ? 'Video Inspection Complete'
                  : processingStatus === 'ANALYZING'
                  ? (analyzingSubStatus || 'Analyzing Video Frames Progressively')
                  : processingStatus === 'CANCELLED'
                  ? 'Analysis Cancelled by User'
                  : 'Inspection Interrupted'}
              </span>
            </div>

            <div className="flex items-center gap-3 font-mono text-[11px] text-slate-400">
              <span>Playback: <strong className="text-white">{formatVideoTime(currentTime)}</strong></span>
              <span>•</span>
              <span>Analyzed: <strong className="text-sky-300">{formatVideoTime(latestAnalyzedTime)}</strong> / {formatVideoTime(videoDuration)}</span>
              <span>•</span>
              <span>Frames: <strong className="text-white">{frameBreakdown.length}</strong></span>
              {processingFps != null && (
                <>
                  <span>•</span>
                  <span>Rate: <strong className="text-cyan-300">{processingFps} FPS</strong></span>
                </>
              )}
            </div>
          </div>

          {/* Timeline Analysis Buffer Progress Bar */}
          <div className="w-full bg-slate-950 rounded-full h-2.5 overflow-hidden border border-slate-800/80 relative">
            <div
              className={`h-full transition-all duration-300 ${
                processingStatus === 'COMPLETED'
                  ? 'bg-emerald-500'
                  : processingStatus === 'FAILED'
                  ? 'bg-rose-500'
                  : processingStatus === 'CANCELLED'
                  ? 'bg-amber-500'
                  : 'bg-sky-500'
              }`}
              style={{
                width: `${Math.min(100, Math.max(0, processingProgressPct || (videoDuration > 0 ? (latestAnalyzedTime / videoDuration) * 100 : 0)))}%`
              }}
            />
          </div>
        </div>
      )}

      {/* 2. Immediate Native Video Player with Progressive AI Overlays */}
      {selectedFile && videoPreviewUrl && (
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-5 lg:p-6 shadow-2xl space-y-5 animate-in fade-in">
          {/* M2.6 Polished Inspection Summary Card */}
          {completionSummary && (
            <div
              className={`p-5 rounded-2xl border flex flex-col gap-4 shadow-xl ${
                completionSummary.overall_compliance_status === 'COMPLIANT'
                  ? 'bg-emerald-950/60 border-emerald-800/80 text-emerald-200'
                  : 'bg-rose-950/60 border-rose-800/80 text-rose-200'
              }`}
            >
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 border-b border-white/10 pb-3">
                <div className="flex items-center gap-3">
                  {completionSummary.overall_compliance_status === 'COMPLIANT' ? (
                    <ShieldCheck className="w-8 h-8 text-emerald-400 flex-shrink-0" />
                  ) : (
                    <ShieldAlert className="w-8 h-8 text-rose-400 flex-shrink-0" />
                  )}
                  <div>
                    <h3 className="font-bold text-sm lg:text-base leading-tight text-white">
                      {completionSummary.overall_compliance_status === 'COMPLIANT'
                        ? 'Inspection Complete: All Workers Fully Compliant'
                        : 'Inspection Complete: Safety Violations Confirmed'}
                    </h3>
                    <p className="text-xs text-slate-300 mt-0.5">
                      Analyzed <strong>{completionSummary.total_frames_processed}</strong> chronological frames ({formatVideoTime(latestAnalyzedTime)} duration). Found{' '}
                      <strong>{completionSummary.total_violations_found}</strong> confirmed violation episode(s).
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Link
                    to="/admin/violations"
                    className="px-3.5 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold border border-slate-700 flex items-center gap-1.5 transition shadow"
                  >
                    <span>Violations Log</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </Link>
                </div>
              </div>

              {/* Authoritative Metric Counters */}
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2.5 text-xs">
                <div className="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
                  <span className="text-[10px] text-slate-400 font-semibold block uppercase tracking-wider">Total Workers</span>
                  <span className="text-base font-bold text-white font-mono mt-0.5 block">{summaryMetrics?.totalWorkers ?? 0}</span>
                </div>
                <div className="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
                  <span className="text-[10px] text-emerald-400 font-semibold block uppercase tracking-wider">Compliant</span>
                  <span className="text-base font-bold text-emerald-400 font-mono mt-0.5 block">{summaryMetrics?.compliantWorkers ?? 0}</span>
                </div>
                <div className="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
                  <span className="text-[10px] text-rose-400 font-semibold block uppercase tracking-wider">Violations</span>
                  <span className="text-base font-bold text-rose-400 font-mono mt-0.5 block">{summaryMetrics?.violationWorkers ?? 0}</span>
                </div>
                <div className="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
                  <span className="text-[10px] text-amber-400 font-semibold block uppercase tracking-wider">Pending/Grace</span>
                  <span className="text-base font-bold text-amber-400 font-mono mt-0.5 block">{summaryMetrics?.uncertainWorkers ?? 0}</span>
                </div>
                <div className="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
                  <span className="text-[10px] text-slate-400 font-semibold block uppercase tracking-wider">Incidents</span>
                  <span className="text-base font-bold text-white font-mono mt-0.5 block">{completionSummary.total_violations_found ?? 0}</span>
                </div>
                <div className="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800/80">
                  <span className="text-[10px] text-sky-400 font-semibold block uppercase tracking-wider">Resolutions</span>
                  <span className="text-base font-bold text-sky-400 font-mono mt-0.5 block">{completionSummary.total_resolutions_found ?? 0}</span>
                </div>
              </div>

              {/* Detected PPE Categories */}
              {summaryMetrics?.detectedCategories?.length > 0 && (
                <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-white/5">
                  <span className="text-[11px] text-slate-300 font-semibold">Detected Equipment:</span>
                  {summaryMetrics.detectedCategories.map((cat, idx) => {
                    const style = getPpeBadgeStyle(cat);
                    return (
                      <span
                        key={idx}
                        className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md text-[11px] font-bold border"
                        style={{
                          backgroundColor: 'rgba(2, 6, 23, 0.75)',
                          borderColor: style.stroke,
                          color: style.stroke
                        }}
                      >
                        <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: style.stroke }}></span>
                        <span>{cat.toUpperCase()}</span>
                      </span>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Main Video Viewport Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            {/* Left 2 Cols: Video Screen with Synchronized Overlays */}
            <div className="lg:col-span-2 space-y-3">
              <div className="relative aspect-video rounded-2xl bg-slate-950 border-2 border-slate-800 overflow-hidden shadow-2xl flex items-center justify-center group">
                {/* Native HTML5 Video Element - Playable Immediately! */}
                <video
                  ref={videoRef}
                  src={videoPreviewUrl}
                  playsInline
                  preload="auto"
                  onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
                  onLoadedMetadata={(e) => {
                    const v = e.currentTarget;
                    if (v.videoWidth && v.videoHeight) {
                      setVideoDimensions({ width: v.videoWidth, height: v.videoHeight });
                    }
                    setVideoDuration(v.duration || 0);
                  }}
                  onPlay={() => setVideoPlaying(true)}
                  onPause={() => setVideoPlaying(false)}
                  onEnded={() => setVideoPlaying(false)}
                  className="w-full h-full object-contain select-none bg-black"
                />

                {/* Synchronized Vector Overlay (SVG) */}
                <svg
                  className="absolute inset-0 w-full h-full pointer-events-none select-none z-10"
                  viewBox={`0 0 ${videoDimensions.width} ${videoDimensions.height}`}
                  preserveAspectRatio="xMidYMid meet"
                >
                  {/* 1. Spatial Zone Polygons */}
                  {showZoneBoundaries &&
                    activeCameraZones.map((m, zIdx) => {
                      const color = getZoneColor(zIdx);
                      const centroid = computePolygonCentroid(m.polygon);
                      return (
                        <g key={m.zoneId || zIdx}>
                          <polygon
                            points={
                              Array.isArray(m.polygon)
                                ? m.polygon.map((pt) => `${pt.x * videoDimensions.width},${pt.y * videoDimensions.height}`).join(' ')
                                : ''
                            }
                            fill={color.fill}
                            stroke={color.stroke}
                            strokeWidth={Math.max(3, Math.round(videoDimensions.width / 450))}
                            strokeDasharray="8 4"
                          />
                          <g
                            transform={`translate(${centroid.x * videoDimensions.width}, ${centroid.y * videoDimensions.height})`}
                          >
                            <rect
                              x="-70"
                              y="-14"
                              width="140"
                              height="28"
                              rx="6"
                              fill="#020617"
                              fillOpacity="0.88"
                              stroke={color.stroke}
                              strokeWidth="1.5"
                            />
                            <text
                              x="0"
                              y="5"
                              textAnchor="middle"
                              fill="#ffffff"
                              fontSize="14"
                              fontWeight="bold"
                              fontFamily="sans-serif"
                            >
                              {m.zoneName || `Zone ${m.zoneId}`}
                            </text>
                          </g>
                        </g>
                      );
                    })}

                  {/* 2. Worker Bounding Boxes & Compliance Badges (Synchronized with active frame) */}
                  {activeFrame?.persons?.map((p, pIdx) => {
                    const bbox = p.bbox || p.boundingBox;
                    if (!bbox || bbox.length < 4) return null;
                    const [x1, y1, x2, y2] = bbox;
                    const w = Math.max(1, x2 - x1);
                    const h = Math.max(1, y2 - y1);

                    const isWorkerViolation = Boolean(p.missing_ppe?.length > 0) || (!p.compliant && !p.uncertain && !p.pending_missing_ppe?.length);
                    const isWorkerUncertain = Boolean(p.uncertain || p.pending_missing_ppe?.length > 0);
                    const isWorkerCompliant = Boolean(p.compliant && !isWorkerViolation && !isWorkerUncertain);

                    const status = isWorkerViolation ? 'VIOLATION' : isWorkerUncertain ? 'UNCERTAIN' : 'COMPLIANT';
                    const style = getComplianceBadgeStyle(status);

                    const missingText = p.missing_ppe?.length ? `MISSING ${p.missing_ppe.join(', ').toUpperCase()}` : '';
                    const pendingText = p.pending_missing_ppe?.length ? `PENDING (${p.pending_missing_ppe.join(', ').toUpperCase()})` : (p.uncertain_reason || 'UNCERTAIN');
                    const labelText = `${p.worker_id || `W-${p.track_id || pIdx + 1}`}: ${
                      isWorkerViolation ? missingText : isWorkerUncertain ? pendingText : 'COMPLIANT'
                    }`;

                    const minDim = Math.min(videoDimensions.width, videoDimensions.height);
                    const fontSize = Math.max(12, Math.round(minDim / 80));
                    const bannerH = Math.max(26, Math.round(fontSize * 1.6));
                    const bannerW = Math.max(labelText.length * (fontSize * 0.62) + 22, 140);
                    const isNearTop = y1 - bannerH < 4;
                    const bannerY = isNearTop ? y1 : y1 - bannerH;
                    const textY = isNearTop ? y1 + fontSize + 4 : y1 - 8;

                    return (
                      <g key={p.track_id || pIdx}>
                        {/* Worker Bounding Box */}
                        <rect
                          x={x1}
                          y={y1}
                          width={w}
                          height={h}
                          fill={style.fill}
                          stroke={style.stroke}
                          strokeWidth={Math.max(2.5, Math.round(minDim / 400))}
                          rx="6"
                        />
                        {/* Header Status Banner Background */}
                        <rect
                          x={x1}
                          y={bannerY}
                          width={bannerW}
                          height={bannerH}
                          fill="#0f172a"
                          fillOpacity="0.94"
                          stroke={style.stroke}
                          strokeWidth="1.5"
                          rx="4"
                        />
                        {/* Left Status Color Accent Pill */}
                        <rect
                          x={x1 + 3}
                          y={bannerY + 3}
                          width={4}
                          height={bannerH - 6}
                          fill={style.stroke}
                          rx="2"
                        />
                        <text
                          x={x1 + 14}
                          y={textY}
                          fill="#ffffff"
                          fontSize={fontSize}
                          fontWeight="bold"
                          fontFamily="ui-sans-serif, system-ui, sans-serif"
                        >
                          {labelText}
                        </text>
                      </g>
                    );
                  })}

                  {/* 3. Detected PPE Gear Overlays (Helmets, Vests, Boots, Goggles, etc.) */}
                  {(activeFrame?.detected_objects || activeFrame?.detected_classes)?.map((obj, objIdx) => {
                    const bbox = obj.bbox;
                    if (!bbox || bbox.length < 4) return null;
                    const [x1, y1, x2, y2] = bbox;
                    const w = Math.max(1, x2 - x1);
                    const h = Math.max(1, y2 - y1);

                    const ppeStyle = getPpeBadgeStyle(obj.name || obj.class);
                    const confPct = Math.round((Number(obj.confidence) || 0) * 100);
                    const labelText = `${(obj.name || obj.class || 'PPE').toUpperCase()} ${confPct}%`;

                    const minDim = Math.min(videoDimensions.width, videoDimensions.height);
                    const ppeFontSize = Math.max(10, Math.round(minDim / 95));
                    const ppeBannerH = Math.max(18, Math.round(ppeFontSize * 1.45));
                    const ppeBannerW = Math.max(45, Math.round(labelText.length * (ppeFontSize * 0.62) + 12));

                    const isNearTop = y1 - ppeBannerH < 4;
                    const bannerY = isNearTop ? y1 : y1 - ppeBannerH;
                    const textY = isNearTop ? y1 + ppeFontSize + 2 : y1 - 4;

                    return (
                      <g key={`ppe-${objIdx}`}>
                        {/* PPE Equipment Bounding Box */}
                        <rect
                          x={x1}
                          y={y1}
                          width={w}
                          height={h}
                          fill={ppeStyle.fill}
                          stroke={ppeStyle.stroke}
                          strokeWidth={Math.max(1.8, Math.round(minDim / 480))}
                          rx="3"
                        />
                        {/* Header Status Tag Banner */}
                        <rect
                          x={x1}
                          y={bannerY}
                          width={ppeBannerW}
                          height={ppeBannerH}
                          fill={ppeStyle.tagBg}
                          rx="2"
                        />
                        <text
                          x={x1 + 6}
                          y={textY}
                          fill={ppeStyle.textFill}
                          fontSize={ppeFontSize}
                          fontWeight="bold"
                          fontFamily="ui-sans-serif, system-ui, sans-serif"
                        >
                          {labelText}
                        </text>
                      </g>
                    );
                  })}
                </svg>

                {/* Analysis-Behind-Playback Floating Indicator when playback moves ahead */}
                {(!activeFrame && isStale) && (
                  <div className="absolute top-3 left-3 right-3 z-30 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 p-3 rounded-2xl bg-amber-950/95 border border-amber-600 text-amber-200 text-xs shadow-2xl backdrop-blur-md animate-in fade-in">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 animate-pulse" />
                      <span>
                        Playback (<strong>{formatVideoTime(currentTime)}</strong>) is ahead of AI analysis (<strong>{formatVideoTime(latestAnalyzedTime)}</strong> analyzed). Overlays suppressed until analysis catches up.
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleSeek(latestAnalyzedTime)}
                      className="self-end sm:self-auto px-3 py-1 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs flex items-center gap-1.5 transition shadow"
                    >
                      <Play className="w-3.5 h-3.5 fill-current" />
                      <span>Jump to Analyzed Front ({formatVideoTime(latestAnalyzedTime)})</span>
                    </button>
                  </div>
                )}

                {/* HUD Status Pill on Top-Right */}
                <div className="absolute top-3 right-3 z-20 flex items-center gap-2">
                  {isProcessing ? (
                    <span className="px-2.5 py-1 rounded-xl text-[11px] font-bold uppercase shadow-lg border backdrop-blur-md bg-sky-950/90 text-sky-300 border-sky-600 animate-pulse flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-ping"></span>
                      <span>ANALYZING ({frameBreakdown.length} frames | {formatVideoTime(latestAnalyzedTime)})</span>
                    </span>
                  ) : (
                    <span className={`px-2.5 py-1 rounded-xl text-[11px] font-bold uppercase shadow-lg border backdrop-blur-md ${
                      activeFrame?.compliance_status === 'COMPLIANT'
                        ? 'bg-emerald-950/80 text-emerald-300 border-emerald-700/60'
                        : activeFrame?.compliance_status === 'VIOLATION'
                        ? 'bg-rose-950/80 text-rose-300 border-rose-700/60'
                        : activeFrame?.compliance_status === 'UNCERTAIN'
                        ? 'bg-amber-950/80 text-amber-300 border-amber-700/60'
                        : 'bg-slate-900/80 text-slate-300 border-slate-700/60'
                    }`}>
                      {activeFrame?.compliance_status || (processingStatus === 'COMPLETED' ? 'COMPLETE' : 'READY')}
                    </span>
                  )}
                </div>
              </div>

              {/* Player Controls & Scrubber */}
              <div className="p-3.5 rounded-2xl bg-slate-950 border border-slate-800 flex flex-col gap-2.5">
                {/* Timeline Scrubber with Dual Analysis Buffer Bar */}
                <div className="flex items-center gap-3">
                  <span className="text-[11px] text-slate-300 font-mono w-24">
                    {formatVideoTime(currentTime)} / {formatVideoTime(videoDuration)}
                  </span>

                  <div className="flex-1 relative flex items-center h-6">
                    {/* Background track */}
                    <div className="absolute inset-x-0 h-1.5 bg-slate-800 rounded-lg overflow-hidden pointer-events-none">
                      {/* Analysis Buffer bar */}
                      <div
                        className="h-full bg-sky-500/50 transition-all duration-200"
                        style={{
                          width: `${videoDuration > 0 ? Math.min(100, (latestAnalyzedTime / videoDuration) * 100) : 0}%`
                        }}
                        title={`AI Analyzed: ${formatVideoTime(latestAnalyzedTime)}`}
                      />
                    </div>

                    {/* Interactive Playhead Slider */}
                    <input
                      type="range"
                      min={0}
                      max={videoDuration || 1}
                      step={0.05}
                      value={currentTime}
                      onChange={(e) => handleSeek(Number(e.target.value))}
                      className="w-full relative z-10 accent-sky-400 h-1.5 bg-transparent rounded-lg cursor-pointer"
                    />
                  </div>

                  <span className="text-[11px] text-slate-400 font-mono w-32 text-right">
                    {(!activeFrame && isStale)
                      ? `Behind AI (${formatVideoTime(latestAnalyzedTime)})`
                      : `Active: ${activeFrame ? `${activeFrame.timestamp_sec.toFixed(1)}s` : `${currentTime.toFixed(1)}s`}`}
                  </span>
                </div>

                {/* Play / Step Buttons & Options */}
                <div className="flex items-center justify-between pt-1">
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleSeek(currentTime - 1.0)}
                      className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 transition"
                      title="Step Back 1.0s"
                    >
                      <SkipBack className="w-4 h-4" />
                    </button>

                    <button
                      type="button"
                      onClick={togglePlayPause}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-bold shadow-md shadow-sky-600/30 transition"
                    >
                      {videoPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                      <span>{videoPlaying ? 'Pause' : 'Play'}</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => handleSeek(currentTime + 1.0)}
                      className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 transition"
                      title="Step Forward 1.0s"
                    >
                      <SkipForward className="w-4 h-4" />
                    </button>

                    <button
                      type="button"
                      onClick={() => handleSeek(0)}
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
                      {[0.5, 1.0, 1.5, 2.0].map((s) => (
                        <button
                          key={s}
                          onClick={() => handleSpeedChange(s)}
                          className={`px-2 py-0.5 rounded text-[11px] ${
                            videoSpeed === s ? 'bg-sky-600 text-white font-bold' : 'bg-slate-800 hover:bg-slate-700'
                          }`}
                        >
                          {s}x
                        </button>
                      ))}
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
                    Synchronized Frame Details
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${
                      (!activeFrame && isStale)
                        ? 'bg-amber-950 text-amber-400 border-amber-800'
                        : activeFrame?.compliance_status === 'COMPLIANT'
                        ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                        : activeFrame?.compliance_status === 'VIOLATION'
                        ? 'bg-rose-950 text-rose-400 border border-rose-800'
                        : activeFrame?.compliance_status === 'UNCERTAIN'
                        ? 'bg-amber-950 text-amber-400 border-amber-800'
                        : 'bg-slate-900 text-slate-400 border border-slate-800'
                    }`}
                  >
                    {(!activeFrame && isStale) ? 'ANALYZING (LAG)' : (activeFrame?.compliance_status || (isProcessing ? 'ANALYZING' : 'READY'))}
                  </span>
                </div>

                {/* Workers in this frame */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-[11px] font-semibold text-slate-300">
                    <span>Workers Present ({(activeFrame?.persons?.length || 0)}):</span>
                    <span className="text-[10px] text-slate-400 font-mono">
                      Timestamp: {activeFrame ? `${activeFrame.timestamp_sec.toFixed(1)}s` : `${currentTime.toFixed(1)}s`}
                    </span>
                  </div>

                  {(!activeFrame && isStale) ? (
                    <div className="p-3 rounded-xl bg-amber-950/40 border border-amber-800/60 text-amber-300 text-xs space-y-2">
                      <p>
                        Playback head ({formatVideoTime(currentTime)}) is ahead of AI analysis ({formatVideoTime(latestAnalyzedTime)} analyzed). Overlays will appear automatically when AI analysis reaches playback position.
                      </p>
                      <button
                        type="button"
                        onClick={() => handleSeek(latestAnalyzedTime)}
                        className="px-2.5 py-1 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-[11px] flex items-center gap-1 transition shadow"
                      >
                        <Play className="w-3 h-3 fill-current" />
                        <span>Jump to Analyzed Front ({formatVideoTime(latestAnalyzedTime)})</span>
                      </button>
                    </div>
                  ) : activeFrame?.persons?.length === 0 ? (
                    <p className="text-xs text-slate-500 italic">No workers in this frame interval.</p>
                  ) : (
                    <div className="space-y-1.5 max-h-44 overflow-y-auto pr-1">
                      {activeFrame?.persons?.map((p, idx) => {
                        const isWorkerViolation = Boolean(p.missing_ppe?.length > 0) || (!p.compliant && !p.uncertain && !p.pending_missing_ppe?.length);
                        const isWorkerUncertain = Boolean(p.uncertain || p.pending_missing_ppe?.length > 0);
                        const isWorkerCompliant = Boolean(p.compliant && !isWorkerViolation && !isWorkerUncertain);

                        return (
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
                              {isWorkerCompliant ? (
                                <span className="text-[10px] font-bold text-emerald-400 bg-emerald-950 px-2 py-0.5 rounded border border-emerald-800">
                                  COMPLIANT
                                </span>
                              ) : isWorkerUncertain ? (
                                <span className="text-[10px] font-bold text-amber-400 bg-amber-950 px-2 py-0.5 rounded border border-amber-800">
                                  {p.pending_missing_ppe?.length ? `PENDING (${p.pending_missing_ppe.join(', ').toUpperCase()})` : (p.uncertain_reason || 'UNCERTAIN')}
                                </span>
                              ) : (
                                <span className="text-[10px] font-bold text-rose-400 bg-rose-950 px-2 py-0.5 rounded border border-rose-800">
                                  MISSING {p.missing_ppe?.join(', ')?.toUpperCase() || 'PPE'}
                                </span>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Individual PPE Equipment Detected in this frame */}
                <div className="space-y-2 pt-2 border-t border-slate-800">
                  <div className="flex items-center justify-between text-[11px] font-semibold text-slate-300">
                    <span className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
                      <span>Detected PPE Gear ({(activeFrame?.detected_objects || activeFrame?.detected_classes || []).length}):</span>
                    </span>
                    <span className="text-[10px] text-slate-400 font-mono">
                      YOLOv8 Objects
                    </span>
                  </div>

                  {(!activeFrame && isStale) ? (
                    <p className="text-xs text-slate-500 italic">Waiting for analysis buffer...</p>
                  ) : (activeFrame?.detected_objects || activeFrame?.detected_classes || []).length === 0 ? (
                    <p className="text-xs text-slate-500 italic">No individual PPE items detected in this interval.</p>
                  ) : (
                    <div className="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto pr-1">
                      {(activeFrame.detected_objects || activeFrame.detected_classes).map((obj, i) => {
                        const style = getPpeBadgeStyle(obj.name || obj.class);
                        const confPct = Math.round((Number(obj.confidence) || 0) * 100);
                        return (
                          <span
                            key={i}
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-bold border"
                            style={{
                              backgroundColor: 'rgba(2, 6, 23, 0.85)',
                              borderColor: style.stroke,
                              color: style.stroke
                            }}
                          >
                            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: style.stroke }}></span>
                            <span>{(obj.name || obj.class).toUpperCase()}</span>
                            <span className="font-mono text-[10px] opacity-80">{confPct}%</span>
                          </span>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              {/* Persisted Incidents Timeline List with Interactive Seek */}
              <div className="p-4 rounded-2xl bg-slate-950 border border-slate-800 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                    <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
                    <span>Persisted Incidents ({persistedIncidents.length})</span>
                  </span>
                  <Link
                    to="/admin/violations"
                    className="text-[11px] text-sky-400 hover:text-sky-300 font-semibold flex items-center gap-0.5"
                  >
                    <span>View All</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </Link>
                </div>

                <div className="space-y-2 max-h-52 overflow-y-auto pr-1">
                  {persistedIncidents.length === 0 ? (
                    <div className="text-center py-4 text-xs text-slate-500">
                      {isProcessing ? 'Monitoring stream for violations...' : 'No violations confirmed during this session.'}
                    </div>
                  ) : (
                    persistedIncidents.map((inc, i) => {
                      const incTime = inc.processingMetadata?.video_timestamp_sec ?? inc.confirmed_timestamp ?? 0;
                      const isResolved = inc.status === 'RESOLVED';
                      const isAck = inc.status === 'ACKNOWLEDGED';
                      return (
                        <div
                          key={inc.episode_id || i}
                          onClick={() => handleSeekToIncident(inc)}
                          className={`p-2.5 rounded-xl cursor-pointer border text-xs space-y-1.5 transition group ${
                            isResolved
                              ? 'bg-slate-900/60 hover:bg-slate-800/80 border-slate-800 hover:border-emerald-700/60'
                              : isAck
                              ? 'bg-slate-900/80 hover:bg-slate-800/80 border-slate-800 hover:border-amber-700/60'
                              : 'bg-slate-900 hover:bg-slate-800/80 border-slate-800 hover:border-rose-700/60'
                          }`}
                          title="Click to jump player to this incident's timestamp"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-white text-xs group-hover:text-sky-300 transition">
                              {inc.worker_id || inc.personId || 'Worker'}
                            </span>
                            <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold border uppercase tracking-wider ${
                              isResolved
                                ? 'bg-emerald-950 text-emerald-400 border-emerald-800'
                                : isAck
                                ? 'bg-amber-950 text-amber-400 border-amber-800'
                                : 'bg-rose-950 text-rose-400 border-rose-800'
                            }`}>
                              {isResolved ? 'RESOLVED' : isAck ? 'ACKNOWLEDGED' : 'CONFIRMED VIOLATION'}
                            </span>
                          </div>
                          <div className="text-[11px] text-slate-400">
                            Missing: <strong className={isResolved ? 'text-slate-300' : 'text-rose-300'}>
                              {Array.isArray(inc.missingPPE) ? inc.missingPPE.join(', ') : inc.missingPPE}
                            </strong> in{' '}
                            {inc.zoneName || 'Monitored Zone'}
                          </div>
                          <div className="text-[10px] text-slate-500 font-mono flex items-center justify-between pt-1 border-t border-slate-800/80">
                            <span>Camera: {inc.cameraName || inc.cameraId}</span>
                            <span className="text-sky-400 font-bold group-hover:underline flex items-center gap-1">
                              <Play className="w-2.5 h-2.5 fill-current" />
                              <span>Jump to t = {Number(incTime).toFixed(1)}s</span>
                            </span>
                          </div>
                        </div>
                      );
                    })
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
