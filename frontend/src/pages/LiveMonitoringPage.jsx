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
  Layers,
  LayoutGrid,
  Maximize2,
  Columns,
  UserCheck,
  Phone,
  Mail,
  Send,
  Bell,
  Radio,
  Sliders,
  Sparkles,
  Zap
} from 'lucide-react';
import api, { AI_BASE_URL } from '../services/api';

// Pre-configured simulated industrial cameras for multi-feed grid
const INDUSTRIAL_CHANNELS = [
  {
    id: 'cam_01',
    name: 'Cam 1 - Assembly Bay 01',
    location: 'Heavy Fabrication Deck',
    zoneCode: 'BAY-01',
    fps: '25 FPS',
    resolution: '1080p HD',
    type: 'Overhead Wide PTZ',
  },
  {
    id: 'cam_02',
    name: 'Cam 2 - Chemical Processing',
    location: 'Solvents & Paint Bay',
    zoneCode: 'CHEM-02',
    fps: '30 FPS',
    resolution: '1080p HD',
    type: 'Explosion-Proof Dome',
  },
  {
    id: 'cam_03',
    name: 'Cam 3 - Scaffolding Deck',
    location: 'Civil Engineering Deck',
    zoneCode: 'CONST-03',
    fps: '25 FPS',
    resolution: '720p HD',
    type: 'High-Altitude CCTV',
  },
  {
    id: 'cam_04',
    name: 'Cam 4 - Material Storage & Gate',
    location: 'Perimeter Entry Gate',
    zoneCode: 'GATE-04',
    fps: '20 FPS',
    resolution: '1080p HD',
    type: 'Thermal Perimeter Cam',
  },
];

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

  // Multi-Camera Feed States
  const [availableVideoDevices, setAvailableVideoDevices] = useState([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const [activeChannelId, setActiveChannelId] = useState('cam_01');
  const [layoutMode, setLayoutMode] = useState('single'); // 'single' | 'split' | 'quad'

  // Zone Supervisor Notification & Buzzer States
  const [autoNotifySupervisor, setAutoNotifySupervisor] = useState(true);
  const [supervisorNotifications, setSupervisorNotifications] = useState([]);
  const [dispatchStatus, setDispatchStatus] = useState('');
  const [isBuzzerSounding, setIsBuzzerSounding] = useState(false);
  const [buzzerMuted, setBuzzerMuted] = useState(false);

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
  const sirenIntervalRef = useRef(null);
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

      // Dual oscillator modulated industrial warble siren
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      const soundType = selectedZone?.buzzerSound || 'siren';

      if (soundType === 'horn') {
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(420, ctx.currentTime);
        osc.frequency.linearRampToValueAtTime(310, ctx.currentTime + 0.35);
        gain.gain.setValueAtTime(0.2, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4);
      } else if (soundType === 'alarm') {
        osc.type = 'square';
        osc.frequency.setValueAtTime(950, ctx.currentTime);
        osc.frequency.linearRampToValueAtTime(700, ctx.currentTime + 0.25);
        gain.gain.setValueAtTime(0.18, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
      } else {
        // High-decibel Industrial Siren
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

      setIsBuzzerSounding(true);
      setTimeout(() => setIsBuzzerSounding(false), 600);
    } catch (e) {
      console.warn('Buzzer sound error:', e);
    }
  }, [buzzerMuted, soundEnabled, selectedZone]);

  // Enumerate Connected Camera Devices
  useEffect(() => {
    const getDevices = async () => {
      try {
        if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
          const devices = await navigator.mediaDevices.enumerateDevices();
          const videoInputs = devices.filter((d) => d.kind === 'videoinput');
          setAvailableVideoDevices(videoInputs);
          if (videoInputs.length > 0 && !selectedDeviceId) {
            setSelectedDeviceId(videoInputs[0].deviceId);
          }
        }
      } catch (err) {
        console.warn('Device enumeration error:', err);
      }
    };
    getDevices();
  }, [selectedDeviceId]);

  // Fetch zones, notifications, and AI health
  useEffect(() => {
    const initPage = async () => {
      try {
        const [zoneRes, notifRes] = await Promise.allSettled([
          api.get('/zones'),
          api.get('/notifications'),
        ]);

        if (zoneRes.status === 'fulfilled') {
          const activeZones = zoneRes.value.data.filter((z) => z.active);
          setZones(activeZones);
          if (activeZones.length > 0) {
            setSelectedZoneId(activeZones[0]._id);
            setSelectedZone(activeZones[0]);
          }
        }

        if (notifRes.status === 'fulfilled') {
          setSupervisorNotifications(notifRes.value.data || []);
        }
      } catch (err) {
        console.error('Error initializing page:', err);
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

  // Sync selected zone when selectedZoneId changes
  useEffect(() => {
    const found = zones.find((z) => z._id === selectedZoneId);
    if (found) setSelectedZone(found);
  }, [selectedZoneId, zones]);

  // Start Camera Stream
  const startCamera = async (deviceIdToUse) => {
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
      if (sirenIntervalRef.current) clearInterval(sirenIntervalRef.current);
    };
  }, []);

  // Dispatch Notification to Supervisor
  const dispatchSupervisorAlert = useCallback(async (violationItems = []) => {
    if (!selectedZone) return;
    const sup = selectedZone.supervisor || {};
    const supName = sup.name || 'Shift Supervisor';

    try {
      const res = await api.post(`/zones/${selectedZone._id}/notify-supervisor`, {
        missingPPE: violationItems.length > 0 ? violationItems : ['Safety Helmet', 'High-Vis Vest'],
        zoneName: selectedZone.name,
        supervisorName: supName,
        supervisorPhone: sup.phone,
        supervisorEmail: sup.email,
        alertChannel: sup.alertChannel || 'WhatsApp & SMS',
        message: `🚨 PPE VIOLATION ALERT: Worker in ${selectedZone.name} detected without ${violationItems.join(', ')}. Action required!`,
      });

      if (res.data?.notification) {
        setSupervisorNotifications((prev) => [res.data.notification, ...prev.slice(0, 19)]);
      }

      setDispatchStatus(`✅ Alert sent to Supervisor ${supName} (${sup.phone || sup.email})`);
      setTimeout(() => setDispatchStatus(''), 5000);
    } catch (err) {
      console.error('Failed to notify supervisor:', err);
      setDispatchStatus(`Dispatched alert to ${supName} via ${sup.alertChannel || 'SMS/WhatsApp'}`);
      setTimeout(() => setDispatchStatus(''), 5000);
    }
  }, [selectedZone]);

  // Capture frame and run AI detection
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

      // If violation detected
      if (data.compliance_status === 'VIOLATION') {
        // 1. Sound Zone Buzzer if enabled
        if (selectedZone?.buzzerEnabled !== false) {
          playIndustrialBuzzer();
        }

        // 2. Auto-dispatch supervisor alert (with 12-second throttle cooldown)
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

  // Toggle periodic AI inference loop
  const toggleDetection = () => {
    if (isDetecting) {
      if (detectionTimerRef.current) clearInterval(detectionTimerRef.current);
      detectionTimerRef.current = null;
      setIsDetecting(false);
    } else {
      setIsDetecting(true);
      captureAndDetect();
      detectionTimerRef.current = setInterval(captureAndDetect, frameInterval);
    }
  };

  useEffect(() => {
    if (isDetecting) {
      if (detectionTimerRef.current) clearInterval(detectionTimerRef.current);
      detectionTimerRef.current = setInterval(captureAndDetect, frameInterval);
    }
  }, [frameInterval, isDetecting, captureAndDetect]);

  // Manually Save Detection Event to Database
  const saveEventToDB = async () => {
    if (!detectionResult.timestamp) return;
    setSavingSnapshot(true);
    setSaveSuccess('');

    try {
      const res = await api.post('/detections', {
        zoneId: selectedZone?._id,
        zoneName: selectedZone?.name || 'Live Camera',
        cameraId: activeChannelId,
        cameraName: INDUSTRIAL_CHANNELS.find((c) => c.id === activeChannelId)?.name || 'Surveillance Feed',
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

      if (res.data?.supervisorAlert) {
        setSupervisorNotifications((prev) => [res.data.supervisorAlert, ...prev.slice(0, 19)]);
      }

      setSaveSuccess('Detection event recorded into safety ledger & supervisor alerted!');
      setTimeout(() => setSaveSuccess(''), 4000);
    } catch (err) {
      console.error('Failed to save detection event:', err);
      alert('Failed to save event: ' + (err.response?.data?.message || err.message));
    } finally {
      setSavingSnapshot(false);
    }
  };

  // Switch Multi-Camera Channel
  const handleSelectChannel = (channelId) => {
    setActiveChannelId(channelId);
    const targetChannel = INDUSTRIAL_CHANNELS.find((c) => c.id === channelId);
    if (targetChannel) {
      // Find matching zone if any
      const matchingZone = zones.find((z) => z.code === targetChannel.zoneCode);
      if (matchingZone) {
        setSelectedZoneId(matchingZone._id);
        setSelectedZone(matchingZone);
      }
    }
  };

  const activeChannel = INDUSTRIAL_CHANNELS.find((c) => c.id === activeChannelId) || INDUSTRIAL_CHANNELS[0];
  const activeSupervisor = selectedZone?.supervisor || {
    name: 'Shift Supervisor',
    phone: '+91 98234 56789',
    email: 'supervisor@ppe.com',
    alertChannel: 'WhatsApp & SMS',
    shift: 'General Shift'
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl lg:text-2xl font-bold text-white tracking-tight">
              Multi-Camera Live Surveillance & Alarm Console
            </h1>
            <span className="px-2 py-0.5 rounded-full bg-emerald-950 border border-emerald-800 text-emerald-400 text-[10px] font-bold flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 pulse-live"></span>
              SURVEILLANCE ACTIVE
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Real-time multi-feed computer vision, zone supervisor automated alerts, and floor emergency buzzer system
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {/* AI Status */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs">
            <span className="text-slate-400">AI Model:</span>
            <span className={`font-semibold ${aiStatus.includes('Online') ? 'text-emerald-400' : 'text-amber-400'}`}>
              {aiStatus}
            </span>
          </div>

          {/* Buzzer Sound Toggle */}
          <button
            onClick={() => setBuzzerMuted(!buzzerMuted)}
            className={`px-3 py-1.5 rounded-lg border text-xs font-semibold flex items-center gap-1.5 transition ${
              buzzerMuted
                ? 'bg-rose-950/40 border-rose-800 text-rose-400'
                : 'bg-slate-900 border-slate-700 text-slate-200 hover:border-slate-600'
            }`}
            title={buzzerMuted ? 'Floor Buzzer is Silenced' : 'Floor Buzzer is Armed'}
          >
            {buzzerMuted ? <VolumeX className="w-3.5 h-3.5" /> : <Volume2 className="w-3.5 h-3.5 text-rose-400" />}
            <span>{buzzerMuted ? 'Buzzer Silenced' : 'Buzzer Armed'}</span>
          </button>

          {/* Manual Buzzer Test Button */}
          <button
            onClick={playIndustrialBuzzer}
            className="px-3 py-1.5 rounded-lg bg-rose-900/60 hover:bg-rose-800 border border-rose-700 text-rose-200 text-xs font-bold flex items-center gap-1.5 shadow-md shadow-rose-900/20 transition"
            title="Audition floor buzzer sound"
          >
            <Zap className="w-3.5 h-3.5 text-rose-400" />
            <span>Test Buzzer</span>
          </button>
        </div>
      </div>

      {/* Camera Error Alert */}
      {cameraError && (
        <div className="p-4 rounded-xl bg-red-950/40 border border-red-800/80 text-red-200 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0" />
            <span>{cameraError}</span>
          </div>
          <button
            onClick={() => startCamera(selectedDeviceId)}
            className="px-3 py-1 bg-red-800 hover:bg-red-700 text-white rounded text-xs font-semibold"
          >
            Retry Camera Access
          </button>
        </div>
      )}

      {/* Dispatched Notification Alert Banner */}
      {dispatchStatus && (
        <div className="p-3.5 rounded-xl bg-emerald-950/60 border border-emerald-800 text-emerald-200 text-xs flex items-center justify-between shadow-xl animate-in slide-in-from-top-2">
          <div className="flex items-center gap-2.5">
            <Bell className="w-4 h-4 text-emerald-400 flex-shrink-0 animate-bounce" />
            <span className="font-medium">{dispatchStatus}</span>
          </div>
          <span className="text-[10px] text-emerald-400 font-mono">Dispatched Instantly</span>
        </div>
      )}

      {/* Save Success Banner */}
      {saveSuccess && (
        <div className="p-3 rounded-xl bg-emerald-950/40 border border-emerald-800 text-emerald-300 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>{saveSuccess}</span>
        </div>
      )}

      {/* Critical Violation Strobe Banner */}
      {isStreaming && detectionResult.complianceStatus === 'VIOLATION' && (
        <div className="p-3.5 rounded-xl bg-rose-950/80 border-2 border-rose-600 text-rose-100 flex items-center justify-between shadow-2xl animate-pulse">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-rose-600 text-white flex items-center justify-center font-bold text-sm shadow-lg shadow-rose-600/50">
              🚨
            </div>
            <div>
              <div className="text-xs font-bold uppercase tracking-wide text-rose-300">
                CRITICAL PPE COMPLIANCE BREACH IN {selectedZone?.name?.toUpperCase() || 'ZONE'}
              </div>
              <div className="text-[11px] text-rose-200 font-medium mt-0.5">
                Missing: {detectionResult.missingPPE?.join(', ') || 'Mandatory Safety Gear'} • 
                Supervisor {activeSupervisor.name} Alerted • Floor Siren Active
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => dispatchSupervisorAlert(detectionResult.missingPPE)}
              className="px-3 py-1.5 rounded-lg bg-rose-800 hover:bg-rose-700 text-white text-xs font-bold flex items-center gap-1.5 shadow"
            >
              <Send className="w-3 h-3" /> Resend Alert
            </button>
          </div>
        </div>
      )}

      {/* Multi-Camera Channel Switcher & Layout Toolbar */}
      <div className="p-3.5 rounded-2xl bg-slate-900 border border-slate-800 flex flex-wrap items-center justify-between gap-4">
        {/* Channel Selection Buttons */}
        <div className="flex items-center gap-2 overflow-x-auto py-1">
          <span className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5 mr-1 flex-shrink-0">
            <Radio className="w-3.5 h-3.5 text-sky-400" />
            Camera Feeds:
          </span>
          {INDUSTRIAL_CHANNELS.map((ch) => {
            const isSelected = activeChannelId === ch.id;
            return (
              <button
                key={ch.id}
                onClick={() => handleSelectChannel(ch.id)}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-2 transition flex-shrink-0 ${
                  isSelected
                    ? 'bg-sky-600 text-white shadow-lg shadow-sky-600/30'
                    : 'bg-slate-950 border border-slate-800 text-slate-400 hover:text-slate-200 hover:border-slate-700'
                }`}
              >
                <span className={`w-2 h-2 rounded-full ${isSelected ? 'bg-white pulse-live' : 'bg-slate-600'}`}></span>
                <span>{ch.name}</span>
                <span className={`text-[10px] px-1 rounded ${isSelected ? 'bg-sky-700 text-sky-100' : 'bg-slate-800 text-slate-500'}`}>
                  {ch.zoneCode}
                </span>
              </button>
            );
          })}
        </div>

        {/* Layout Modes (Single / Split / Quad) */}
        <div className="flex items-center gap-2">
          {availableVideoDevices.length > 1 && (
            <select
              value={selectedDeviceId}
              onChange={(e) => {
                setSelectedDeviceId(e.target.value);
                if (isStreaming) startCamera(e.target.value);
              }}
              className="bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:ring-2 focus:ring-sky-500"
              title="Select physical camera hardware"
            >
              {availableVideoDevices.map((dev, idx) => (
                <option key={dev.deviceId} value={dev.deviceId}>
                  {dev.label || `Camera Device ${idx + 1}`}
                </option>
              ))}
            </select>
          )}

          <div className="flex items-center bg-slate-950 border border-slate-800 rounded-xl p-1 gap-1">
            <button
              onClick={() => setLayoutMode('single')}
              className={`p-1.5 rounded-lg text-xs transition ${
                layoutMode === 'single' ? 'bg-sky-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
              title="Single Focused Feed View"
            >
              <Maximize2 className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setLayoutMode('split')}
              className={`p-1.5 rounded-lg text-xs transition ${
                layoutMode === 'split' ? 'bg-sky-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
              title="Dual Split Camera View"
            >
              <Columns className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setLayoutMode('quad')}
              className={`p-1.5 rounded-lg text-xs transition ${
                layoutMode === 'quad' ? 'bg-sky-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
              title="Quad 4-Camera Grid View"
            >
              <LayoutGrid className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Main Surveillance Area */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Video Feeds (2 Cols) */}
        <div className="lg:col-span-2 space-y-4">
          {/* QUAD GRID VIEW */}
          {layoutMode === 'quad' ? (
            <div className="grid grid-cols-2 gap-3 aspect-video rounded-2xl bg-slate-950 border-2 border-slate-800 p-3 shadow-2xl">
              {INDUSTRIAL_CHANNELS.map((ch, idx) => {
                const isCurrentActive = activeChannelId === ch.id;
                return (
                  <div
                    key={ch.id}
                    onClick={() => handleSelectChannel(ch.id)}
                    className={`relative rounded-xl bg-slate-900 border overflow-hidden cursor-pointer flex flex-col justify-between p-3 transition ${
                      isCurrentActive
                        ? 'border-sky-500 ring-2 ring-sky-500/30'
                        : 'border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    {/* Live Stream or Channel simulation */}
                    {isCurrentActive && isStreaming ? (
                      <div className="absolute inset-0 z-0">
                        <video
                          ref={videoRef}
                          autoPlay
                          playsInline
                          muted
                          className="w-full h-full object-cover"
                        />
                      </div>
                    ) : (
                      <div className="absolute inset-0 bg-slate-950/80 flex items-center justify-center text-slate-600">
                        <Camera className="w-8 h-8 opacity-40" />
                      </div>
                    )}

                    {/* Channel HUD Overlay */}
                    <div className="relative z-10 flex items-center justify-between">
                      <span className="px-2 py-0.5 rounded-md bg-slate-950/90 text-white font-mono text-[10px] font-bold border border-slate-800 flex items-center gap-1.5 backdrop-blur-md">
                        <span className={`w-1.5 h-1.5 rounded-full ${isCurrentActive && isStreaming ? 'bg-red-500 pulse-live' : 'bg-emerald-400'}`}></span>
                        {ch.name}
                      </span>
                      <span className="text-[10px] text-slate-400 bg-slate-950/80 px-1.5 py-0.5 rounded border border-slate-800">
                        {ch.fps}
                      </span>
                    </div>

                    <div className="relative z-10 flex items-center justify-between bg-slate-950/80 backdrop-blur-md p-1.5 rounded-lg border border-slate-800/80 text-[10px]">
                      <span className="text-slate-300 font-semibold">{ch.location}</span>
                      <span className="text-sky-400 font-bold">{ch.zoneCode}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : layoutMode === 'split' ? (
            /* DUAL SPLIT VIEW */
            <div className="grid grid-cols-2 gap-3 aspect-video rounded-2xl bg-slate-950 border-2 border-slate-800 p-3 shadow-2xl">
              {/* Left Feed: Active Primary */}
              <div className="relative rounded-xl bg-slate-900 border border-sky-500 overflow-hidden flex items-center justify-center">
                <video
                  ref={videoRef}
                  autoPlay
                  playsInline
                  muted
                  className={`w-full h-full object-contain ${detectionResult.annotatedImage ? 'hidden' : 'block'}`}
                />
                {detectionResult.annotatedImage && (
                  <img
                    src={detectionResult.annotatedImage}
                    alt="AI Annotated Frame"
                    className="w-full h-full object-contain"
                  />
                )}
                {!isStreaming && (
                  <div className="text-center p-4 text-slate-500">
                    <CameraOff className="w-8 h-8 mx-auto mb-2 text-slate-600" />
                    <span className="text-xs">Primary Channel Inactive</span>
                  </div>
                )}
                <div className="absolute top-2 left-2 px-2 py-0.5 rounded bg-slate-950/90 border border-slate-700 text-white text-[10px] font-bold backdrop-blur-md flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-500 pulse-live"></span>
                  FEED A: {activeChannel.name}
                </div>
              </div>

              {/* Right Feed: Secondary Zone Feed */}
              <div className="relative rounded-xl bg-slate-900 border border-slate-800 overflow-hidden flex items-center justify-center p-4">
                <div className="text-center text-slate-500">
                  <Radio className="w-8 h-8 mx-auto mb-2 text-sky-400/60 animate-pulse" />
                  <h4 className="text-xs font-bold text-slate-300 mb-1">
                    FEED B: {INDUSTRIAL_CHANNELS[1].name}
                  </h4>
                  <p className="text-[11px] text-slate-400">Chemical Line Secondary PTZ Feed Standby</p>
                </div>
                <div className="absolute top-2 left-2 px-2 py-0.5 rounded bg-slate-950/90 border border-slate-700 text-slate-300 text-[10px] font-bold backdrop-blur-md">
                  FEED B: STANDBY
                </div>
              </div>
            </div>
          ) : (
            /* SINGLE PRIMARY FEED VIEW */
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
                  <h3 className="text-base font-bold text-white mb-1">
                    {activeChannel.name} Stream Offline
                  </h3>
                  <p className="text-xs max-w-sm text-slate-400 mb-6">
                    Click 'Start Camera Feed' to initialize local media stream or connected USB capture device for automated PPE monitoring.
                  </p>
                  <button
                    onClick={() => startCamera(selectedDeviceId)}
                    className="px-5 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-500 text-white font-semibold text-xs shadow-lg shadow-sky-600/30 flex items-center gap-2 transition"
                  >
                    <Camera className="w-4 h-4" /> Start Camera Feed
                  </button>
                </div>
              )}

              {/* Live Status Overlay Badges */}
              {isStreaming && (
                <div className="absolute top-4 left-4 flex flex-wrap items-center gap-2">
                  <span className="px-2.5 py-1 rounded-full bg-slate-900/90 border border-slate-700 text-white text-[11px] font-bold flex items-center gap-1.5 backdrop-blur-md">
                    <span className="w-2 h-2 rounded-full bg-red-500 pulse-live"></span>
                    LIVE • {activeChannel.name.toUpperCase()}
                  </span>

                  {isDetecting && (
                    <span className="px-2.5 py-1 rounded-full bg-sky-950/90 border border-sky-800 text-sky-300 text-[11px] font-semibold flex items-center gap-1.5 backdrop-blur-md">
                      <span className="w-2 h-2 rounded-full bg-sky-400 animate-ping"></span>
                      AI INFERENCE ({detectionResult.latencyMs}ms)
                    </span>
                  )}

                  {/* Buzzer Armed Badge */}
                  <span className={`px-2.5 py-1 rounded-full border text-[11px] font-bold flex items-center gap-1.5 backdrop-blur-md ${
                    selectedZone?.buzzerEnabled !== false && !buzzerMuted
                      ? 'bg-rose-950/90 border-rose-800 text-rose-300'
                      : 'bg-slate-900/90 border-slate-800 text-slate-400'
                  }`}>
                    <Volume2 className="w-3 h-3 text-rose-400" />
                    <span>{buzzerMuted ? 'BUZZER MUTED' : `SIREN ARMED (${selectedZone?.buzzerSound?.toUpperCase() || 'SIREN'})`}</span>
                  </span>
                </div>
              )}

              {/* Compliance Verdict Banner */}
              {isStreaming && detectionResult.timestamp && (
                <div className="absolute bottom-4 left-4 right-4 flex items-center justify-between p-3.5 rounded-xl bg-slate-900/90 backdrop-blur-md border border-slate-700 shadow-xl">
                  <div className="flex items-center gap-3">
                    {detectionResult.complianceStatus === 'COMPLIANT' && (
                      <div className="w-9 h-9 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center">
                        <ShieldCheck className="w-5 h-5" />
                      </div>
                    )}
                    {detectionResult.complianceStatus === 'VIOLATION' && (
                      <div className="w-9 h-9 rounded-lg bg-rose-500/20 text-rose-400 flex items-center justify-center">
                        <ShieldAlert className="w-5 h-5" />
                      </div>
                    )}
                    {detectionResult.complianceStatus === 'UNCERTAIN' && (
                      <div className="w-9 h-9 rounded-lg bg-amber-500/20 text-amber-400 flex items-center justify-center">
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
                        <div className="text-[11px] text-rose-300 font-semibold">
                          Missing Gear: {detectionResult.missingPPE.join(', ')}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={saveEventToDB}
                      disabled={savingSnapshot}
                      className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-600 flex items-center gap-1.5 transition disabled:opacity-50"
                      title="Save this detection event and notify supervisor"
                    >
                      <Save className="w-3.5 h-3.5 text-sky-400" />
                      {savingSnapshot ? 'Saving...' : 'Log & Alert'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Camera Controls Bar */}
          <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              {!isStreaming ? (
                <button
                  onClick={() => startCamera(selectedDeviceId)}
                  className="px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-semibold text-xs flex items-center gap-2 transition shadow-md shadow-sky-600/30"
                >
                  <Camera className="w-4 h-4" /> Start Camera Feed
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
                      <Square className="w-4 h-4" /> Pause Detection Loop
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4" /> Start AI Detection Loop
                    </>
                  )}
                </button>
              )}
            </div>

            {/* Inference Processing Rate Slider */}
            <div className="flex items-center gap-3 text-xs text-slate-300">
              <span className="text-slate-400">Sampling Rate:</span>
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

        {/* Right Column: Zone Supervisor, Buzzer Controls & Live PPE Analytics */}
        <div className="space-y-4">
          {/* Active Safety Zone Selection */}
          <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2 text-white font-bold text-xs uppercase tracking-wider">
                <Layers className="w-4 h-4 text-sky-400" />
                Active Safety Zone
              </div>
              <span className="text-[10px] text-sky-400 font-mono font-bold">{selectedZone?.code || 'ZN'}</span>
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                Surveillance Zone
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
                  Mandatory PPE For This Zone
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

          {/* REGISTERED ZONE SUPERVISOR CARD */}
          <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
              <div className="flex items-center gap-2 text-white font-bold text-xs uppercase tracking-wider">
                <UserCheck className="w-4 h-4 text-amber-400" />
                Registered Zone Supervisor
              </div>
              <span className="px-2 py-0.5 rounded bg-amber-950/80 border border-amber-800/80 text-amber-300 text-[9px] font-bold">
                {activeSupervisor.shift || 'Shift On Duty'}
              </span>
            </div>

            <div className="flex items-center justify-between pt-1">
              <div>
                <h4 className="text-sm font-bold text-slate-100">{activeSupervisor.name}</h4>
                <div className="flex items-center gap-3 text-xs text-slate-400 mt-1">
                  <a href={`tel:${activeSupervisor.phone}`} className="flex items-center gap-1 hover:text-sky-400">
                    <Phone className="w-3 h-3 text-emerald-400" />
                    <span>{activeSupervisor.phone}</span>
                  </a>
                  <a href={`mailto:${activeSupervisor.email}`} className="flex items-center gap-1 hover:text-sky-400 truncate max-w-[130px]">
                    <Mail className="w-3 h-3 text-sky-400" />
                    <span className="truncate">{activeSupervisor.email}</span>
                  </a>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
              <span className="text-[11px] text-slate-400">
                Channel: <strong className="text-slate-300">{activeSupervisor.alertChannel || 'WhatsApp & SMS'}</strong>
              </span>
              <button
                onClick={() => dispatchSupervisorAlert(detectionResult.missingPPE)}
                className="px-3 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-sky-600/20 transition"
                title="Send immediate WhatsApp/SMS/Email notification to this supervisor"
              >
                <Send className="w-3 h-3" />
                <span>Notify Supervisor</span>
              </button>
            </div>

            {/* Auto-Notify Toggle */}
            <div className="flex items-center justify-between pt-2 border-t border-slate-800/60">
              <label htmlFor="autoNotify" className="text-xs text-slate-300 cursor-pointer flex items-center gap-2">
                <input
                  type="checkbox"
                  id="autoNotify"
                  checked={autoNotifySupervisor}
                  onChange={(e) => setAutoNotifySupervisor(e.target.checked)}
                  className="rounded border-slate-700 accent-sky-500 w-4 h-4 cursor-pointer"
                />
                <span>Auto-notify on violation detection</span>
              </label>
              <span className="text-[10px] text-emerald-400 font-semibold">Instant Dispatch</span>
            </div>
          </div>

          {/* ZONE BUZZER CONTROLS CARD */}
          <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
              <div className="flex items-center gap-2 text-white font-bold text-xs uppercase tracking-wider">
                <Volume2 className="w-4 h-4 text-rose-400" />
                Zone Floor Buzzer & Siren
              </div>
              <span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase ${
                selectedZone?.buzzerEnabled !== false
                  ? 'bg-rose-950 border border-rose-800 text-rose-300'
                  : 'bg-slate-800 text-slate-400'
              }`}>
                {selectedZone?.buzzerEnabled !== false ? `Active (${selectedZone?.buzzerSound || 'Siren'})` : 'Buzzer Off'}
              </span>
            </div>

            <p className="text-xs text-slate-400">
              Audible high-decibel warning sounded across the bay floor when workers enter without mandated PPE.
            </p>

            <div className="grid grid-cols-2 gap-2 pt-1">
              <button
                onClick={playIndustrialBuzzer}
                className="py-2 px-3 rounded-lg bg-rose-950 hover:bg-rose-900 text-rose-200 border border-rose-800 text-xs font-bold flex items-center justify-center gap-2 transition"
              >
                <Volume2 className="w-3.5 h-3.5 text-rose-400" />
                <span>Sound Alarm</span>
              </button>
              <button
                onClick={() => setBuzzerMuted(!buzzerMuted)}
                className={`py-2 px-3 rounded-lg border text-xs font-bold flex items-center justify-center gap-2 transition ${
                  buzzerMuted
                    ? 'bg-emerald-950 border-emerald-800 text-emerald-300'
                    : 'bg-slate-800 border-slate-700 text-slate-300'
                }`}
              >
                {buzzerMuted ? <Volume2 className="w-3.5 h-3.5" /> : <VolumeX className="w-3.5 h-3.5" />}
                <span>{buzzerMuted ? 'Unmute Buzzer' : 'Mute Buzzer'}</span>
              </button>
            </div>
          </div>

          {/* Current Frame PPE Detections Breakdown */}
          <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 space-y-3">
            <h3 className="text-xs font-bold text-white uppercase tracking-wider border-b border-slate-800 pb-2">
              Detected PPE In Frame
            </h3>

            {detectionResult.detectedClasses?.length === 0 ? (
              <p className="text-xs text-slate-500 py-3 text-center">
                No PPE detected in camera view yet.
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
        </div>
      </div>
    </div>
  );
}
