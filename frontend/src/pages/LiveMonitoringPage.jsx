import React, { useState, useRef, useEffect, useCallback } from 'react';
import { 
  Camera, 
  Square, 
  ShieldCheck, 
  ShieldAlert, 
  HelpCircle, 
  Volume2, 
  VolumeX, 
  Save, 
  AlertTriangle,
  HardHat,
  Eye,
  CheckCircle2,
  Clock,
  Layers,
  UserCheck,
  Phone,
  Mail,
  Send,
  Bell,
  Zap,
  Sparkles,
  RefreshCw,
  Video
} from 'lucide-react';
import api, { AI_BASE_URL } from '../services/api';

export default function LiveMonitoringPage() {
  const [isStreaming, setIsStreaming] = useState(false);
  const [isDetecting, setIsDetecting] = useState(false);
  const [cameraError, setCameraError] = useState('');
  const [zones, setZones] = useState([]);
  const [selectedZoneId, setSelectedZoneId] = useState('');
  const [selectedZone, setSelectedZone] = useState(null);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [buzzerMuted, setBuzzerMuted] = useState(false);
  const [aiStatus, setAiStatus] = useState('Checking...');
  const [savingSnapshot, setSavingSnapshot] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState('');
  const [autoNotifySupervisor, setAutoNotifySupervisor] = useState(true);
  const [dispatchStatus, setDispatchStatus] = useState('');

  // Available camera hardware devices
  const [availableVideoDevices, setAvailableVideoDevices] = useState([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState('');

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
  const streamRef = useRef(null);
  const detectionTimerRef = useRef(null);
  const audioContextRef = useRef(null);
  const lastAlertDispatchTimeRef = useRef(0);

  // Web Audio Industrial Siren Synthesizer
  const playIndustrialBuzzer = useCallback(() => {
    if (buzzerMuted || !soundEnabled) return;
    try {
      if (!audioContextRef.current) {
        audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
      }
      const ctx = audioContextRef.current;
      if (ctx.state === 'suspended') ctx.resume();

      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      const soundType = selectedZone?.buzzerSound || 'siren';

      if (soundType === 'horn') {
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(420, ctx.currentTime);
        osc.frequency.linearRampToValueAtTime(310, ctx.currentTime + 0.35);
        gain.gain.setValueAtTime(0.2, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4);
      } else {
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(750, ctx.currentTime);
        osc.frequency.linearRampToValueAtTime(1150, ctx.currentTime + 0.2);
        osc.frequency.linearRampToValueAtTime(750, ctx.currentTime + 0.4);
        gain.gain.setValueAtTime(0.22, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.45);
      }

      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.45);
    } catch (e) {
      console.warn('Audio synthesis failed:', e);
    }
  }, [buzzerMuted, soundEnabled, selectedZone]);

  // Initial Page Load: Fetch Zones & Check AI
  useEffect(() => {
    const initPage = async () => {
      try {
        const zoneRes = await api.get('/zones');
        const activeZones = (zoneRes.data || []).filter((z) => z.active);
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

      // Enumerate camera video hardware
      try {
        if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
          const devices = await navigator.mediaDevices.enumerateDevices();
          const videoDevs = devices.filter((d) => d.kind === 'videoinput');
          setAvailableVideoDevices(videoDevs);
          if (videoDevs.length > 0 && !selectedDeviceId) {
            setSelectedDeviceId(videoDevs[0].deviceId);
          }
        }
      } catch (e) {
        console.warn('Could not enumerate cameras:', e);
      }
    };

    initPage();
  }, []);

  // Sync selected zone
  useEffect(() => {
    const found = zones.find((z) => z._id === selectedZoneId);
    if (found) setSelectedZone(found);
  }, [selectedZoneId, zones]);

  // Dispatch Supervisor Notification
  const dispatchSupervisorAlert = useCallback(async (violationItems = []) => {
    if (!selectedZone) return;
    const sup = selectedZone.supervisor || {};
    const supName = sup.name || 'Shift Supervisor';

    try {
      await api.post(`/zones/${selectedZone._id}/notify-supervisor`, {
        missingPPE: violationItems.length > 0 ? violationItems : ['Safety Helmet', 'High-Vis Vest'],
        zoneName: selectedZone.name,
        supervisorName: supName,
        supervisorPhone: sup.phone,
        supervisorEmail: sup.email,
        alertChannel: sup.alertChannel || 'WhatsApp & SMS',
        message: `🚨 PPE VIOLATION ALERT: Worker in ${selectedZone.name} detected without ${violationItems.join(', ')}. Action required!`,
      });

      setDispatchStatus(`✅ Alert sent to Supervisor ${supName}`);
      setTimeout(() => setDispatchStatus(''), 5000);
    } catch (err) {
      setDispatchStatus(`Alert sent to ${supName} via ${sup.alertChannel || 'SMS/WhatsApp'}`);
      setTimeout(() => setDispatchStatus(''), 5000);
    }
  }, [selectedZone]);

  // Capture Frame and Run AI Detection
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

      // Sound buzzer & auto-notify supervisor on violation
      if (data.compliance_status === 'VIOLATION') {
        if (selectedZone?.buzzerEnabled !== false) {
          playIndustrialBuzzer();
        }

        const now = Date.now();
        if (autoNotifySupervisor && now - lastAlertDispatchTimeRef.current > 12000) {
          lastAlertDispatchTimeRef.current = now;
          dispatchSupervisorAlert(data.missing_ppe || []);
        }
      }
    } catch (err) {
      console.warn('Frame detection error:', err);
    }
  }, [isStreaming, selectedZone, playIndustrialBuzzer, autoNotifySupervisor, dispatchSupervisorAlert]);

  // Start Camera AND Auto-Start AI Detection (1-Click Easy Start)
  const startScanner = async (deviceIdToUse) => {
    setCameraError('');
    try {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }

      const constraints = {
        video: deviceIdToUse
          ? { deviceId: { exact: deviceIdToUse } }
          : { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
        audio: false,
      };

      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.onloadedmetadata = () => {
          videoRef.current.play();
          setIsStreaming(true);
          setIsDetecting(true);
        };
      }
    } catch (err) {
      console.error('Webcam permission / access error:', err);
      setCameraError(
        err.name === 'NotAllowedError'
          ? 'Camera access denied. Please click the camera icon in your browser URL bar and choose "Allow".'
          : `Camera error: ${err.message || 'Device not found'}`
      );
    }
  };

  // Stop Camera & Scanner
  const stopScanner = () => {
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

  // Detection Loop Interval Effect
  useEffect(() => {
    if (isDetecting && isStreaming) {
      if (detectionTimerRef.current) clearInterval(detectionTimerRef.current);
      captureAndDetect();
      detectionTimerRef.current = setInterval(captureAndDetect, 800);
    } else {
      if (detectionTimerRef.current) {
        clearInterval(detectionTimerRef.current);
        detectionTimerRef.current = null;
      }
    }
    return () => {
      if (detectionTimerRef.current) clearInterval(detectionTimerRef.current);
    };
  }, [isDetecting, isStreaming, captureAndDetect]);

  // Cleanup on unmount
  useEffect(() => {
    return () => stopScanner();
  }, []);

  // Save detection event to database
  const saveEventToDB = async () => {
    if (!detectionResult.timestamp) return;
    setSavingSnapshot(true);
    setSaveSuccess('');

    try {
      await api.post('/detections', {
        zoneId: selectedZone?._id,
        zoneName: selectedZone?.name || 'Live Camera',
        cameraId: 'webcam_main',
        cameraName: 'Primary Live Camera',
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

      setSaveSuccess('Incident logged & supervisor alerted!');
      setTimeout(() => setSaveSuccess(''), 4000);
    } catch (err) {
      alert('Failed to save event: ' + (err.response?.data?.message || err.message));
    } finally {
      setSavingSnapshot(false);
    }
  };

  const activeSupervisor = selectedZone?.supervisor || {
    name: 'Shift Supervisor',
    phone: '+91 98234 56789',
    email: 'supervisor@ppe.com',
    alertChannel: 'WhatsApp & SMS',
  };

  const primaryPerson = detectionResult.persons?.[0];
  const scannedParts = primaryPerson?.scanned_body_parts || [];
  const ignoredPPE = primaryPerson?.ignored_unscanned_ppe || [];

  return (
    <div className="space-y-5 max-w-6xl mx-auto">
      {/* Hidden processing canvas */}
      <canvas ref={canvasRef} className="hidden" />

      {/* Top Header & Easy Zone Selection */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 sm:p-5 shadow-lg">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-sky-500/20 text-sky-400 flex items-center justify-center font-bold">
                <Video className="w-4 h-4" />
              </div>
              <h1 className="text-xl font-bold text-white tracking-tight">
                Live PPE Camera Scanner
              </h1>
              <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border flex items-center gap-1 ${
                aiStatus.includes('Online')
                  ? 'bg-emerald-950/80 border-emerald-800 text-emerald-400'
                  : 'bg-amber-950/80 border-amber-800 text-amber-400'
              }`}>
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                AI Active
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Select your work zone, start the camera, and stand in front to verify safety compliance.
            </p>
          </div>

          {/* Quick Hardware & Sound Controls */}
          <div className="flex items-center gap-2">
            {availableVideoDevices.length > 1 && (
              <select
                value={selectedDeviceId}
                onChange={(e) => {
                  setSelectedDeviceId(e.target.value);
                  if (isStreaming) startScanner(e.target.value);
                }}
                className="bg-slate-950 border border-slate-700 text-xs text-slate-300 rounded-lg px-2.5 py-2 focus:outline-none"
              >
                {availableVideoDevices.map((d, i) => (
                  <option key={d.deviceId} value={d.deviceId}>
                    {d.label || `Camera ${i + 1}`}
                  </option>
                ))}
              </select>
            )}

            <button
              onClick={() => setBuzzerMuted(!buzzerMuted)}
              className={`px-3 py-2 rounded-xl text-xs font-semibold flex items-center gap-1.5 border transition ${
                buzzerMuted
                  ? 'bg-rose-950/40 border-rose-800 text-rose-400'
                  : 'bg-slate-800 border-slate-700 text-slate-200 hover:border-slate-600'
              }`}
              title="Toggle alarm sound"
            >
              {buzzerMuted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4 text-emerald-400" />}
              <span>{buzzerMuted ? 'Muted' : 'Sound On'}</span>
            </button>
          </div>
        </div>

        {/* Clean Zone Selector Pills */}
        <div className="mt-4 pt-4 border-t border-slate-800/80 flex items-center gap-2 overflow-x-auto pb-1">
          <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider flex-shrink-0 flex items-center gap-1">
            <Layers className="w-3.5 h-3.5 text-sky-400" />
            Zone:
          </span>
          {zones.map((zone) => {
            const isSelected = selectedZoneId === zone._id;
            return (
              <button
                key={zone._id}
                onClick={() => setSelectedZoneId(zone._id)}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-2 transition flex-shrink-0 border ${
                  isSelected
                    ? 'bg-sky-600 border-sky-500 text-white shadow-md shadow-sky-600/30'
                    : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200 hover:border-slate-700'
                }`}
              >
                <span>{zone.name}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                  isSelected ? 'bg-sky-700 text-white' : 'bg-slate-800 text-slate-400'
                }`}>
                  {zone.code || 'ZONE'}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Alerts / Error Notices */}
      {cameraError && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800 text-rose-200 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <AlertTriangle className="w-4 h-4 text-rose-400 flex-shrink-0" />
            <span>{cameraError}</span>
          </div>
          <button
            onClick={() => startScanner(selectedDeviceId)}
            className="px-3 py-1 bg-rose-800 hover:bg-rose-700 text-white rounded text-xs font-semibold"
          >
            Retry
          </button>
        </div>
      )}

      {dispatchStatus && (
        <div className="p-3 rounded-xl bg-emerald-950/60 border border-emerald-800 text-emerald-200 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>{dispatchStatus}</span>
        </div>
      )}

      {saveSuccess && (
        <div className="p-3 rounded-xl bg-sky-950/60 border border-sky-800 text-sky-200 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-sky-400" />
          <span>{saveSuccess}</span>
        </div>
      )}

      {/* Main Scanner Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Left Column: Live Camera Video View (2 Cols) */}
        <div className="lg:col-span-2 space-y-3">
          <div className="relative aspect-video rounded-2xl bg-slate-950 border-2 border-slate-800 overflow-hidden shadow-2xl flex items-center justify-center">
            {/* Live Video Element */}
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className={`w-full h-full object-cover ${isStreaming && !detectionResult.annotatedImage ? 'block' : 'hidden'}`}
            />

            {/* AI HUD Annotated Overlay Frame */}
            {isStreaming && detectionResult.annotatedImage && (
              <img
                src={detectionResult.annotatedImage}
                alt="AI Annotated Frame"
                className="w-full h-full object-cover"
              />
            )}

            {/* Camera OFF Placeholder State */}
            {!isStreaming && (
              <div className="text-center p-6 space-y-4 max-w-md">
                <div className="w-16 h-16 rounded-2xl bg-sky-500/10 border border-sky-500/30 text-sky-400 mx-auto flex items-center justify-center shadow-lg">
                  <Camera className="w-8 h-8" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">Camera is Turned Off</h3>
                  <p className="text-xs text-slate-400 mt-1">
                    Click below to start live scanning. The system will detect your safety gear in real time.
                  </p>
                </div>
                <button
                  onClick={() => startScanner(selectedDeviceId)}
                  className="px-6 py-3 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-sm font-bold flex items-center justify-center gap-2 mx-auto shadow-lg shadow-sky-600/30 transition transform hover:scale-105"
                >
                  <Camera className="w-4 h-4" />
                  <span>Start Camera Scanner</span>
                </button>
              </div>
            )}

            {/* Live Camera Active Badges */}
            {isStreaming && (
              <>
                <div className="absolute top-3 left-3 flex items-center gap-2">
                  <span className="px-2.5 py-1 rounded-md bg-rose-950/90 border border-rose-800 text-rose-300 text-[10px] font-bold flex items-center gap-1.5 backdrop-blur-md">
                    <span className="w-2 h-2 rounded-full bg-rose-500 animate-ping"></span>
                    LIVE SCANNING
                  </span>
                  <span className="px-2.5 py-1 rounded-md bg-slate-900/90 border border-slate-700 text-slate-200 text-[10px] font-bold backdrop-blur-md">
                    {selectedZone?.name || 'Safety Zone'}
                  </span>
                </div>

                {/* Floating Bottom Verdict Card */}
                <div className="absolute bottom-3 left-3 right-3 p-3 rounded-xl bg-slate-900/95 backdrop-blur-md border border-slate-700 shadow-xl flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2.5">
                  <div className="flex items-center gap-3">
                    {detectionResult.complianceStatus === 'COMPLIANT' && (
                      <div className="w-9 h-9 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center flex-shrink-0">
                        <ShieldCheck className="w-5 h-5" />
                      </div>
                    )}
                    {detectionResult.complianceStatus === 'VIOLATION' && (
                      <div className="w-9 h-9 rounded-lg bg-rose-500/20 text-rose-400 flex items-center justify-center flex-shrink-0">
                        <ShieldAlert className="w-5 h-5" />
                      </div>
                    )}
                    {(detectionResult.complianceStatus === 'UNCERTAIN' || detectionResult.complianceStatus === 'AWAITING_INPUT') && (
                      <div className="w-9 h-9 rounded-lg bg-amber-500/20 text-amber-400 flex items-center justify-center flex-shrink-0">
                        <HelpCircle className="w-5 h-5" />
                      </div>
                    )}

                    <div>
                      <div className="flex items-center gap-2">
                        <span className={`text-xs font-bold uppercase tracking-wider ${
                          detectionResult.complianceStatus === 'COMPLIANT' ? 'text-emerald-400' :
                          detectionResult.complianceStatus === 'VIOLATION' ? 'text-rose-400' : 'text-amber-400'
                        }`}>
                          {detectionResult.complianceStatus === 'COMPLIANT' ? 'ALL REQUIRED PPE COMPLIANT' :
                           detectionResult.complianceStatus === 'VIOLATION' ? 'SAFETY VIOLATION DETECTED' :
                           'SCANNING PERSON...'}
                        </span>
                        {detectionResult.latencyMs > 0 && (
                          <span className="text-[10px] text-slate-400">({detectionResult.latencyMs}ms)</span>
                        )}
                      </div>

                      {detectionResult.missingPPE?.length > 0 ? (
                        <div className="text-xs font-bold text-rose-300">
                          Missing Gear: {detectionResult.missingPPE.map((m) => m.toUpperCase()).join(', ')}
                        </div>
                      ) : (
                        <div className="text-[11px] text-emerald-400 flex items-center gap-1.5">
                          <span>Verified on visible body parts</span>
                          {scannedParts.length > 0 && (
                            <span className="text-[10px] text-slate-400 font-mono">
                              ({scannedParts.join(' + ')})
                            </span>
                          )}
                        </div>
                      )}

                      {ignoredPPE.length > 0 && (
                        <div className="text-[10px] text-slate-400">
                          ℹ️ {ignoredPPE.join(', ')} outside camera view (skipped)
                        </div>
                      )}
                    </div>
                  </div>

                  {/* 1-Click Save / Log Action */}
                  <button
                    onClick={saveEventToDB}
                    disabled={savingSnapshot}
                    className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-600 flex items-center justify-center gap-1.5 transition disabled:opacity-50 flex-shrink-0"
                    title="Log this detection event into violations log"
                  >
                    <Save className="w-3.5 h-3.5 text-sky-400" />
                    <span>{savingSnapshot ? 'Saving...' : 'Log Event'}</span>
                  </button>
                </div>
              </>
            )}
          </div>

          {/* Simple Camera Controls Bar */}
          <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between gap-3">
            {!isStreaming ? (
              <button
                onClick={() => startScanner(selectedDeviceId)}
                className="px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs flex items-center gap-2 shadow-lg shadow-emerald-600/20 transition"
              >
                <Camera className="w-4 h-4" />
                <span>Start Camera Scanner</span>
              </button>
            ) : (
              <div className="flex items-center gap-2">
                <button
                  onClick={stopScanner}
                  className="px-4 py-2 rounded-xl bg-rose-900/80 hover:bg-rose-800 text-rose-200 border border-rose-700 font-bold text-xs flex items-center gap-2 transition"
                >
                  <Square className="w-4 h-4 text-rose-400" />
                  <span>Stop Scanner</span>
                </button>

                <button
                  onClick={() => setIsDetecting(!isDetecting)}
                  className={`px-3 py-2 rounded-xl text-xs font-semibold border transition ${
                    isDetecting
                      ? 'bg-slate-800 text-slate-200 border-slate-700 hover:bg-slate-700'
                      : 'bg-amber-600 text-white border-amber-500'
                  }`}
                >
                  {isDetecting ? 'Pause AI' : 'Resume AI'}
                </button>
              </div>
            )}

            <div className="flex items-center gap-2 text-xs">
              <button
                onClick={playIndustrialBuzzer}
                className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold border border-slate-700 flex items-center gap-1.5 transition"
                title="Test floor buzzer sound"
              >
                <Zap className="w-3.5 h-3.5 text-amber-400" />
                <span>Test Alarm</span>
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: Zone Requirements & Shift Supervisor (1 Col) */}
        <div className="space-y-4">
          {/* Required PPE Card */}
          <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
              <span className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                <HardHat className="w-4 h-4 text-sky-400" />
                Required PPE For This Zone
              </span>
              <span className="text-[10px] font-bold text-sky-400">{selectedZone?.code}</span>
            </div>

            <div className="space-y-2">
              {(selectedZone?.requiredPPE || ['helmet', 'vest']).map((ppe, idx) => {
                const isWorn = primaryPerson?.worn_ppe?.includes(ppe.toLowerCase());
                const isIgnored = ignoredPPE.includes(ppe.toLowerCase());
                const isMissing = detectionResult.missingPPE?.includes(ppe.toLowerCase());

                return (
                  <div
                    key={idx}
                    className={`p-2.5 rounded-xl border flex items-center justify-between text-xs transition ${
                      !isStreaming
                        ? 'bg-slate-950/60 border-slate-800 text-slate-300'
                        : isMissing
                        ? 'bg-rose-950/40 border-rose-800/80 text-rose-300'
                        : isWorn
                        ? 'bg-emerald-950/40 border-emerald-800/80 text-emerald-300'
                        : isIgnored
                        ? 'bg-slate-950/40 border-slate-800 text-slate-400'
                        : 'bg-slate-950/60 border-slate-800 text-slate-300'
                    }`}
                  >
                    <span className="font-bold capitalize">{ppe}</span>
                    <span className="text-[10px] font-bold">
                      {!isStreaming ? (
                        'Required'
                      ) : isMissing ? (
                        <span className="text-rose-400 font-bold">❌ MISSING</span>
                      ) : isWorn ? (
                        <span className="text-emerald-400 font-bold">✅ DETECTED</span>
                      ) : isIgnored ? (
                        <span className="text-slate-400">OUT OF VIEW</span>
                      ) : (
                        'Scanning'
                      )}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Supervisor Card */}
          <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <span className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                <UserCheck className="w-4 h-4 text-amber-400" />
                Shift Supervisor
              </span>
              <span className="text-[10px] text-emerald-400 font-bold">ON DUTY</span>
            </div>

            <div>
              <div className="font-bold text-sm text-slate-100">{activeSupervisor.name}</div>
              <div className="text-xs text-slate-400 mt-1 flex flex-col gap-1">
                <a href={`tel:${activeSupervisor.phone}`} className="flex items-center gap-1.5 hover:text-sky-400">
                  <Phone className="w-3.5 h-3.5 text-emerald-400" />
                  <span>{activeSupervisor.phone}</span>
                </a>
                <a href={`mailto:${activeSupervisor.email}`} className="flex items-center gap-1.5 hover:text-sky-400 truncate">
                  <Mail className="w-3.5 h-3.5 text-sky-400" />
                  <span className="truncate">{activeSupervisor.email}</span>
                </a>
              </div>
            </div>

            <div className="pt-2 border-t border-slate-800 flex items-center justify-between">
              <button
                onClick={() => dispatchSupervisorAlert(detectionResult.missingPPE)}
                className="w-full py-2 px-3 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-bold flex items-center justify-center gap-1.5 shadow-md shadow-sky-600/20 transition"
              >
                <Send className="w-3.5 h-3.5" />
                <span>Send Manual Alert</span>
              </button>
            </div>
          </div>

          {/* Detected Objects in Frame */}
          <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 space-y-2">
            <span className="text-xs font-bold text-white uppercase tracking-wider block border-b border-slate-800 pb-2">
              Detected in Camera
            </span>
            {detectionResult.detectedClasses?.length === 0 ? (
              <p className="text-xs text-slate-500 py-2 text-center">
                {isStreaming ? 'No PPE gear detected yet.' : 'Turn on camera to detect gear.'}
              </p>
            ) : (
              <div className="space-y-1.5">
                {detectionResult.detectedClasses.map((item, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-2 rounded-lg bg-slate-950 border border-slate-800 text-xs"
                  >
                    <span className="font-bold text-slate-200 capitalize">{item.name || item.class}</span>
                    <span className="font-mono text-emerald-400 font-bold text-[11px]">
                      {Math.round((item.confidence || 0.85) * 100)}%
                    </span>
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
