import React, { useState, useRef, useEffect, useCallback } from 'react';
import { 
  Camera, 
  CameraOff, 
  Play, 
  Square, 
  ShieldCheck, 
  ShieldAlert, 
  HelpCircle, 
  Settings2, 
  Volume2, 
  VolumeX, 
  RefreshCw, 
  Save, 
  AlertTriangle,
  HardHat,
  Eye,
  CheckCircle2,
  Clock,
  Layers
} from 'lucide-react';
import api, { AI_BASE_URL } from '../services/api';

export default function LiveMonitoringPage() {
  const [isStreaming, setIsStreaming] = useState(false);
  const [isDetecting, setIsDetecting] = useState(false);
  const [cameraError, setCameraError] = useState('');
  const [zones, setZones] = useState([]);
  const [selectedZoneId, setSelectedZoneId] = useState('');
  const [selectedZone, setSelectedZone] = useState(null);
  const [frameInterval, setFrameInterval] = useState(800); // ms
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [aiStatus, setAiStatus] = useState('Checking...');
  const [savingSnapshot, setSavingSnapshot] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState('');

  // AI Detection State
  const [detectionResult, setDetectionResult] = useState({
    complianceStatus: 'AWAITING_INPUT',
    missingPPE: [],
    detectedClasses: [],
    persons: [],
    annotatedImage: null,
    latencyMs: 0,
    timestamp: null,
  });

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const overlayCanvasRef = useRef(null);
  const streamRef = useRef(null);
  const detectionTimerRef = useRef(null);
  const audioContextRef = useRef(null);

  // Play audio beep on violation
  const playAlertSound = useCallback(() => {
    if (!soundEnabled) return;
    try {
      if (!audioContextRef.current) {
        audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
      }
      const ctx = audioContextRef.current;
      if (ctx.state === 'suspended') ctx.resume();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(880, ctx.currentTime); // 880 Hz
      gain.gain.setValueAtTime(0.15, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.3);
    } catch (e) {
      console.warn('Audio alert error:', e);
    }
  }, [soundEnabled]);

  // Fetch zones and check AI health on mount
  useEffect(() => {
    const initPage = async () => {
      try {
        const zoneRes = await api.get('/zones');
        const activeZones = zoneRes.data.filter((z) => z.active);
        setZones(activeZones);
        if (activeZones.length > 0) {
          setSelectedZoneId(activeZones[0]._id);
          setSelectedZone(activeZones[0]);
        }
      } catch (err) {
        console.error('Error fetching zones:', err);
      }

      try {
        const aiRes = await fetch(`${AI_BASE_URL}/health`);
        if (aiRes.ok) {
          const data = await aiRes.json();
          setAiStatus(`Online (${data.model_type || 'YOLOv8'})`);
        } else {
          setAiStatus('Offline');
        }
      } catch (err) {
        setAiStatus('Offline');
      }
    };

    initPage();
  }, []);

  // Update selected zone object when ID changes
  useEffect(() => {
    const found = zones.find((z) => z._id === selectedZoneId);
    if (found) setSelectedZone(found);
  }, [selectedZoneId, zones]);

  // Start Camera Stream
  const startCamera = async () => {
    setCameraError('');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          facingMode: 'user',
        },
        audio: false,
      });

      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.onloadedmetadata = () => {
          videoRef.current.play();
          setIsStreaming(true);
        };
      }
    } catch (err) {
      console.error('Webcam permission / access error:', err);
      setCameraError(
        err.name === 'NotAllowedError'
          ? 'Camera permission denied. Please allow camera access in browser settings.'
          : `Camera error: ${err.message || 'Device not found'}`
      );
    }
  };

  // Stop Camera Stream
  const stopCamera = () => {
    if (detectionTimerRef.current) {
      clearInterval(detectionTimerRef.current);
      detectionTimerRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setIsStreaming(false);
    setIsDetecting(false);
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, []);

  // Send single frame to AI service
  const captureAndDetect = useCallback(async () => {
    if (!videoRef.current || !canvasRef.current || !isStreaming) return;

    const video = videoRef.current;
    if (video.readyState !== 4) return;

    const canvas = canvasRef.current;
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const base64Data = canvas.toDataURL('image/jpeg', 0.85);

    try {
      const startTime = performance.now();
      const res = await fetch(`${AI_BASE_URL}/detect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image: base64Data,
          required_ppe: selectedZone?.requiredPPE || ['helmet', 'vest'],
          zone_name: selectedZone?.name || 'Live Surveillance',
          confidence_threshold: 0.35,
        }),
      });

      if (!res.ok) throw new Error('AI detection endpoint failed');
      const data = await res.json();
      const duration = Math.round(performance.now() - startTime);

      setDetectionResult({
        complianceStatus: data.compliance_status || 'UNCERTAIN',
        missingPPE: data.missing_ppe || [],
        detectedClasses: data.detected_classes || [],
        persons: data.persons || [],
        annotatedImage: data.annotated_image ? `data:image/jpeg;base64,${data.annotated_image}` : null,
        latencyMs: duration,
        timestamp: new Date().toLocaleTimeString(),
      });

      // Beep if violation detected
      if (data.compliance_status === 'VIOLATION') {
        playAlertSound();
      }
    } catch (err) {
      console.warn('Frame detection error:', err);
    }
  }, [isStreaming, selectedZone, playAlertSound]);

  // Start / Stop periodic AI inference loop
  const toggleDetection = () => {
    if (isDetecting) {
      if (detectionTimerRef.current) clearInterval(detectionTimerRef.current);
      detectionTimerRef.current = null;
      setIsDetecting(false);
    } else {
      setIsDetecting(true);
      captureAndDetect(); // trigger immediate first frame
      detectionTimerRef.current = setInterval(captureAndDetect, frameInterval);
    }
  };

  // Re-adjust interval if changed while running
  useEffect(() => {
    if (isDetecting) {
      if (detectionTimerRef.current) clearInterval(detectionTimerRef.current);
      detectionTimerRef.current = setInterval(captureAndDetect, frameInterval);
    }
  }, [frameInterval, isDetecting, captureAndDetect]);

  // Manually Save Detection Event to Backend DB
  const saveEventToDB = async () => {
    if (!detectionResult.timestamp) return;
    setSavingSnapshot(true);
    setSaveSuccess('');

    try {
      await api.post('/detections', {
        zoneId: selectedZone?._id,
        zoneName: selectedZone?.name || 'Live Camera',
        sourceType: 'webcam',
        detectedClasses: detectionResult.detectedClasses,
        missingPPE: detectionResult.missingPPE,
        complianceStatus: detectionResult.complianceStatus,
        personCount: detectionResult.persons?.length || 1,
        evidenceImageBase64: detectionResult.annotatedImage || canvasRef.current?.toDataURL('image/jpeg', 0.8),
        processingMetadata: {
          latencyMs: detectionResult.latencyMs,
          model: 'YOLOv8',
        },
      });

      setSaveSuccess('Detection event recorded into safety ledger!');
      setTimeout(() => setSaveSuccess(''), 4000);
    } catch (err) {
      console.error('Failed to save detection event:', err);
      alert('Failed to save event to database: ' + (err.response?.data?.message || err.message));
    } finally {
      setSavingSnapshot(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl lg:text-2xl font-bold text-white tracking-tight">Real-Time PPE Camera Surveillance</h1>
          <p className="text-xs text-slate-400 mt-1">Autonomous computer vision feed analysis and safety enforcement</p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs">
            <span className="text-slate-400">AI Service:</span>
            <span className={`font-semibold ${aiStatus.includes('Online') ? 'text-emerald-400' : 'text-amber-400'}`}>
              {aiStatus}
            </span>
          </div>

          <button
            onClick={() => setSoundEnabled(!soundEnabled)}
            className={`p-2 rounded-lg border text-xs flex items-center gap-1.5 transition ${
              soundEnabled
                ? 'bg-slate-800 border-slate-700 text-sky-400'
                : 'bg-slate-900 border-slate-800 text-slate-500'
            }`}
            title={soundEnabled ? 'Audio Alert Beep Enabled' : 'Audio Alert Muted'}
          >
            {soundEnabled ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {cameraError && (
        <div className="p-4 rounded-xl bg-red-950/40 border border-red-800/80 text-red-200 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0" />
            <span>{cameraError}</span>
          </div>
          <button
            onClick={startCamera}
            className="px-3 py-1 bg-red-800 hover:bg-red-700 text-white rounded text-xs font-semibold"
          >
            Retry Permission
          </button>
        </div>
      )}

      {saveSuccess && (
        <div className="p-3 rounded-xl bg-emerald-950/40 border border-emerald-800 text-emerald-300 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>{saveSuccess}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Video Stream Viewer (2 columns) */}
        <div className="lg:col-span-2 space-y-4">
          <div className="relative aspect-video rounded-2xl bg-slate-950 border-2 border-slate-800 overflow-hidden shadow-2xl flex items-center justify-center">
            {/* Native Video Feed */}
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className={`w-full h-full object-contain ${detectionResult.annotatedImage ? 'hidden' : 'block'}`}
            />

            {/* AI Annotated Feed Overlay */}
            {detectionResult.annotatedImage && (
              <img
                src={detectionResult.annotatedImage}
                alt="AI Annotated Frame"
                className="w-full h-full object-contain"
              />
            )}

            {/* Hidden capture canvas */}
            <canvas ref={canvasRef} className="hidden" />

            {/* Offline / Inactive Placeholder */}
            {!isStreaming && (
              <div className="absolute inset-0 flex flex-col items-center justify-center p-6 text-center bg-slate-950/90 text-slate-400">
                <div className="w-16 h-16 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-center mb-4 text-slate-500">
                  <CameraOff className="w-8 h-8" />
                </div>
                <h3 className="text-base font-bold text-white mb-1">Webcam Feed Inactive</h3>
                <p className="text-xs max-w-sm text-slate-400 mb-6">
                  Click 'Start Camera' to initialize browser media stream and begin real-time PPE object detection.
                </p>
                <button
                  onClick={startCamera}
                  className="px-5 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-500 text-white font-semibold text-xs shadow-lg shadow-sky-600/30 flex items-center gap-2 transition"
                >
                  <Camera className="w-4 h-4" /> Start Camera
                </button>
              </div>
            )}

            {/* Live Status Overlay Badges */}
            {isStreaming && (
              <div className="absolute top-4 left-4 flex items-center gap-2">
                <span className="px-2.5 py-1 rounded-full bg-slate-900/90 border border-slate-700 text-white text-[11px] font-bold flex items-center gap-1.5 backdrop-blur-md">
                  <span className="w-2 h-2 rounded-full bg-red-500 pulse-live"></span>
                  LIVE CAMERA
                </span>
                {isDetecting && (
                  <span className="px-2.5 py-1 rounded-full bg-sky-950/90 border border-sky-800 text-sky-300 text-[11px] font-semibold flex items-center gap-1.5 backdrop-blur-md">
                    <span className="w-2 h-2 rounded-full bg-sky-400 animate-ping"></span>
                    AI INFERENCE ({detectionResult.latencyMs}ms)
                  </span>
                )}
              </div>
            )}

            {/* Live Compliance Verdict Banner */}
            {isStreaming && detectionResult.timestamp && (
              <div className="absolute bottom-4 left-4 right-4 flex items-center justify-between p-3 rounded-xl bg-slate-900/90 backdrop-blur-md border border-slate-700">
                <div className="flex items-center gap-3">
                  {detectionResult.complianceStatus === 'COMPLIANT' && (
                    <div className="w-8 h-8 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center">
                      <ShieldCheck className="w-5 h-5" />
                    </div>
                  )}
                  {detectionResult.complianceStatus === 'VIOLATION' && (
                    <div className="w-8 h-8 rounded-lg bg-rose-500/20 text-rose-400 flex items-center justify-center">
                      <ShieldAlert className="w-5 h-5" />
                    </div>
                  )}
                  {detectionResult.complianceStatus === 'UNCERTAIN' && (
                    <div className="w-8 h-8 rounded-lg bg-amber-500/20 text-amber-400 flex items-center justify-center">
                      <HelpCircle className="w-5 h-5" />
                    </div>
                  )}

                  <div>
                    <div className="flex items-center gap-2">
                      <span className={`text-xs font-bold uppercase tracking-wider ${
                        detectionResult.complianceStatus === 'COMPLIANT' ? 'text-emerald-400' :
                        detectionResult.complianceStatus === 'VIOLATION' ? 'text-rose-400' : 'text-amber-400'
                      }`}>
                        {detectionResult.complianceStatus}
                      </span>
                      <span className="text-[10px] text-slate-400">@ {detectionResult.timestamp}</span>
                    </div>
                    {detectionResult.missingPPE?.length > 0 && (
                      <div className="text-[11px] text-rose-300 font-medium">
                        Missing: {detectionResult.missingPPE.join(', ')}
                      </div>
                    )}
                  </div>
                </div>

                <button
                  onClick={saveEventToDB}
                  disabled={savingSnapshot}
                  className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-600 flex items-center gap-1.5 transition disabled:opacity-50"
                  title="Record this detection event in the MongoDB database"
                >
                  <Save className="w-3.5 h-3.5 text-sky-400" />
                  {savingSnapshot ? 'Saving...' : 'Log Event'}
                </button>
              </div>
            )}
          </div>

          {/* Camera Controls Bar */}
          <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              {!isStreaming ? (
                <button
                  onClick={startCamera}
                  className="px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-semibold text-xs flex items-center gap-2 transition shadow-md shadow-sky-600/30"
                >
                  <Camera className="w-4 h-4" /> Start Camera
                </button>
              ) : (
                <button
                  onClick={stopCamera}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-red-400 font-semibold text-xs flex items-center gap-2 border border-slate-700 transition"
                >
                  <Square className="w-4 h-4" /> Stop Camera
                </button>
              )}

              {isStreaming && (
                <button
                  onClick={toggleDetection}
                  className={`px-4 py-2 rounded-lg font-semibold text-xs flex items-center gap-2 transition ${
                    isDetecting
                      ? 'bg-amber-600 hover:bg-amber-500 text-white shadow-md shadow-amber-600/30'
                      : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-md shadow-emerald-600/30'
                  }`}
                >
                  {isDetecting ? (
                    <>
                      <Square className="w-4 h-4" /> Pause Detection
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4" /> Start AI Detection
                    </>
                  )}
                </button>
              )}
            </div>

            {/* Frame Rate Throttling Slider */}
            <div className="flex items-center gap-3 text-xs text-slate-300">
              <span className="text-slate-400">Processing Rate:</span>
              <input
                type="range"
                min="400"
                max="2000"
                step="200"
                value={frameInterval}
                onChange={(e) => setFrameInterval(Number(e.target.value))}
                className="w-28 accent-sky-500"
              />
              <span className="font-mono text-sky-400 w-12 text-right">{frameInterval}ms</span>
            </div>
          </div>
        </div>

        {/* Sidebar Controls & Real-Time Analytics (1 column) */}
        <div className="space-y-4">
          {/* Zone Configuration Card */}
          <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2 text-white font-bold text-xs uppercase tracking-wider">
                <Layers className="w-4 h-4 text-sky-400" />
                Active Surveillance Zone
              </div>
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                Select Safety Zone
              </label>
              <select
                value={selectedZoneId}
                onChange={(e) => setSelectedZoneId(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
              >
                {zones.map((z) => (
                  <option key={z._id} value={z._id}>
                    {z.name} ({z.code || 'ZONE'})
                  </option>
                ))}
              </select>
            </div>

            {selectedZone && (
              <div>
                <span className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
                  Required PPE for this Zone
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {selectedZone.requiredPPE?.map((item, idx) => (
                    <span
                      key={idx}
                      className="px-2.5 py-1 rounded-md bg-slate-800 text-sky-300 text-[11px] font-medium border border-slate-700 uppercase"
                    >
                      {item}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Current Frame Detections Breakdown */}
          <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 space-y-3">
            <h3 className="text-xs font-bold text-white uppercase tracking-wider border-b border-slate-800 pb-2">
              Detected PPE Objects
            </h3>

            {detectionResult.detectedClasses?.length === 0 ? (
              <p className="text-xs text-slate-500 py-4 text-center">
                No PPE detected in current field of view.
              </p>
            ) : (
              <div className="space-y-2">
                {detectionResult.detectedClasses.map((item, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-2 rounded-lg bg-slate-950/60 border border-slate-800 text-xs"
                  >
                    <span className="font-semibold text-slate-200 capitalize">{item.name || item.class}</span>
                    <span className="font-mono text-emerald-400 font-bold text-[11px]">
                      {Math.round((item.confidence || 0.85) * 100)}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Person-to-PPE Association Card */}
          <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 space-y-3">
            <h3 className="text-xs font-bold text-white uppercase tracking-wider border-b border-slate-800 pb-2">
              Worker Compliance Status
            </h3>

            {detectionResult.persons?.length === 0 ? (
              <p className="text-xs text-slate-500 py-4 text-center">
                Waiting for worker detection...
              </p>
            ) : (
              <div className="space-y-2">
                {detectionResult.persons.map((p, idx) => (
                  <div
                    key={idx}
                    className={`p-3 rounded-lg border text-xs space-y-1 ${
                      p.compliant
                        ? 'bg-emerald-950/20 border-emerald-800/40'
                        : 'bg-rose-950/20 border-rose-800/40'
                    }`}
                  >
                    <div className="flex items-center justify-between font-bold">
                      <span className="text-slate-200">Worker #{idx + 1}</span>
                      <span className={p.compliant ? 'text-emerald-400' : 'text-rose-400'}>
                        {p.compliant ? 'COMPLIANT' : 'VIOLATION'}
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-400">
                      Gear Worn: {p.worn_ppe?.join(', ') || 'None'}
                    </div>
                    {p.missing_ppe?.length > 0 && (
                      <div className="text-[11px] text-rose-300 font-semibold">
                        Missing: {p.missing_ppe.join(', ')}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
