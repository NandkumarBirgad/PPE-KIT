import React, { useState, useEffect } from 'react';
import { 
  Settings, 
  Cpu, 
  Server, 
  ShieldCheck, 
  Sliders, 
  BellRing, 
  CheckCircle2, 
  AlertCircle, 
  RefreshCw,
  Save,
  HelpCircle,
  Activity,
  HardHat,
  Volume2,
  Lock,
  Eye,
  Radio
} from 'lucide-react';
import api, { AI_BASE_URL } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { canEditCameraPolygons } from '../services/cameraPolygonService';

const AVAILABLE_PPE = [
  { id: 'helmet', label: 'Safety Helmet / Hard Hat' },
  { id: 'vest', label: 'High-Visibility Safety Vest' },
  { id: 'boots', label: 'Steel-Toe Safety Boots' },
  { id: 'goggles', label: 'Protective Safety Goggles' },
  { id: 'gloves', label: 'Heavy-Duty Work Gloves' },
  { id: 'mask', label: 'Respiratory Dust Mask' }
];

export default function SettingsPage() {
  const { user } = useAuth();
  const isAdmin = canEditCameraPolygons(user);

  // Settings state
  const [factoryName, setFactoryName] = useState('Antigravity PPE Monitoring Facility');
  const [defaultRequiredPpe, setDefaultRequiredPpe] = useState(['helmet', 'vest', 'boots']);
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.35);
  const [violationConfirmationDurationSec, setViolationConfirmationDurationSec] = useState(3.0);
  const [incidentAutoResolutionDurationSec, setIncidentAutoResolutionDurationSec] = useState(2.0);
  const [videoSamplingInterval, setVideoSamplingInterval] = useState(1000);
  const [alertCooldown, setAlertCooldown] = useState(5);
  const [floorBuzzerEnabled, setFloorBuzzerEnabled] = useState(true);
  const [soundEnabled, setSoundEnabled] = useState(true);

  // Camera health settings
  const [cameraWarningTimeoutSec, setCameraWarningTimeoutSec] = useState(5.0);
  const [cameraOfflineTimeoutSec, setCameraOfflineTimeoutSec] = useState(15.0);
  const [cameraDegradedFailures, setCameraDegradedFailures] = useState(3);

  // UI state
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState('');
  const [saveError, setSaveError] = useState('');

  // Diagnostics state
  const [testingBackend, setTestingBackend] = useState(false);
  const [backendResult, setBackendResult] = useState(null);
  const [testingAi, setTestingAi] = useState(false);
  const [aiResult, setAiResult] = useState(null);

  // Fetch settings from authoritative backend
  const fetchSettings = async () => {
    setLoading(true);
    setSaveError('');
    try {
      const res = await api.get('/settings');
      const data = res.data || {};
      if (data.factory_name) setFactoryName(data.factory_name);
      if (Array.isArray(data.default_required_ppe)) setDefaultRequiredPpe(data.default_required_ppe);
      if (data.confidence_threshold !== undefined) setConfidenceThreshold(Number(data.confidence_threshold));
      if (data.violation_confirmation_duration_sec !== undefined) {
        setViolationConfirmationDurationSec(Number(data.violation_confirmation_duration_sec));
      }
      if (data.incident_auto_resolution_duration_sec !== undefined) {
        setIncidentAutoResolutionDurationSec(Number(data.incident_auto_resolution_duration_sec));
      }
      if (data.video_sampling_interval_ms !== undefined) setVideoSamplingInterval(Number(data.video_sampling_interval_ms));
      if (data.alert_cooldown_sec !== undefined) setAlertCooldown(Number(data.alert_cooldown_sec));
      if (data.floor_buzzer_enabled !== undefined) setFloorBuzzerEnabled(Boolean(data.floor_buzzer_enabled));
      if (data.sound_enabled !== undefined) setSoundEnabled(Boolean(data.sound_enabled));
      if (data.camera_warning_timeout_sec !== undefined) setCameraWarningTimeoutSec(Number(data.camera_warning_timeout_sec));
      if (data.camera_offline_timeout_sec !== undefined) setCameraOfflineTimeoutSec(Number(data.camera_offline_timeout_sec));
      if (data.camera_degraded_failures !== undefined) setCameraDegradedFailures(Number(data.camera_degraded_failures));
    } catch (err) {
      console.error('Fetch settings error:', err);
      setSaveError(err.response?.data?.message || 'Failed to load system settings from backend.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSettings();
    testServices();
  }, []);

  const testServices = async () => {
    setTestingBackend(true);
    try {
      const res = await api.get('/health');
      setBackendResult({ status: 'Online', message: res.data?.service || 'Flask API Server Healthy' });
    } catch (err) {
      setBackendResult({ status: 'Offline', message: err.message || 'Cannot reach API backend' });
    } finally {
      setTestingBackend(false);
    }

    setTestingAi(true);
    try {
      const res = await fetch(`${AI_BASE_URL}/health`);
      if (res.ok) {
        const data = await res.json();
        setAiResult({
          status: 'Online',
          model: data.model_type || 'YOLOv8 PPE Model',
          device: data.device || 'CPU',
        });
      } else {
        setAiResult({ status: 'Error', message: 'Inference service reported an error' });
      }
    } catch (err) {
      setAiResult({ status: 'Offline', message: 'AI inference service is not responding' });
    } finally {
      setTestingAi(false);
    }
  };

  const handleTogglePpe = (id) => {
    if (!isAdmin) return;
    if (defaultRequiredPpe.includes(id)) {
      setDefaultRequiredPpe(defaultRequiredPpe.filter((item) => item !== id));
    } else {
      setDefaultRequiredPpe([...defaultRequiredPpe, id]);
    }
  };

  const handleSave = async () => {
    if (!isAdmin) return;
    setSaving(true);
    setSaveSuccess('');
    setSaveError('');

    const payload = {
      factory_name: factoryName.trim(),
      default_required_ppe: defaultRequiredPpe,
      confidence_threshold: Number(confidenceThreshold),
      violation_confirmation_duration_sec: Number(violationConfirmationDurationSec),
      incident_auto_resolution_duration_sec: Number(incidentAutoResolutionDurationSec),
      video_sampling_interval_ms: Number(videoSamplingInterval),
      alert_cooldown_sec: Number(alertCooldown),
      floor_buzzer_enabled: Boolean(floorBuzzerEnabled),
      sound_enabled: Boolean(soundEnabled),
      camera_warning_timeout_sec: Number(cameraWarningTimeoutSec),
      camera_offline_timeout_sec: Number(cameraOfflineTimeoutSec),
      camera_degraded_failures: Number(cameraDegradedFailures)
    };

    try {
      const res = await api.put('/settings', payload);
      setSaveSuccess(res.data?.message || 'Configuration parameters persisted successfully across restarts!');
      setTimeout(() => setSaveSuccess(''), 5000);
    } catch (err) {
      console.error('Save settings error:', err);
      setSaveError(err.response?.data?.message || 'Failed to save settings to database.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl lg:text-2xl font-bold text-white tracking-tight">System Infrastructure Settings</h1>
            <span className="px-2 py-0.5 rounded-full bg-sky-950 border border-sky-800 text-sky-400 text-[10px] font-bold">
              Backend Authoritative
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Configure factory-wide PPE policies, temporal thresholds, camera health timeouts, and persistent database storage
          </p>
        </div>

        {!isAdmin && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-amber-950/40 border border-amber-800 text-amber-300 text-xs font-medium">
            <Lock className="w-3.5 h-3.5" />
            <span>Supervisor Operational View (Read-Only)</span>
          </div>
        )}
      </div>

      {/* Notifications */}
      {saveSuccess && (
        <div className="p-3.5 rounded-xl bg-emerald-950/60 border border-emerald-700 text-emerald-200 text-xs flex items-center gap-2 shadow-lg animate-in fade-in">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
          <span className="font-semibold">{saveSuccess}</span>
        </div>
      )}

      {saveError && (
        <div className="p-3.5 rounded-xl bg-rose-950/60 border border-rose-800 text-rose-200 text-xs flex items-center gap-2 shadow-lg animate-in fade-in">
          <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
          <span className="font-semibold">{saveError}</span>
        </div>
      )}

      {/* 1. Service Health Diagnostics */}
      <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2 font-bold text-white text-xs uppercase tracking-wider">
            <Server className="w-4 h-4 text-sky-400" />
            Service Health Checks
          </div>
          <button
            onClick={testServices}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 border border-slate-700 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${testingBackend || testingAi ? 'animate-spin' : ''}`} /> Re-test Diagnostics
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
          <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-white">Flask Backend API</span>
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                backendResult?.status === 'Online'
                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                  : 'bg-rose-950 text-rose-400 border border-rose-800'
              }`}>
                {testingBackend ? 'Checking...' : backendResult?.status || 'Unknown'}
              </span>
            </div>
            <p className="text-slate-400 text-[11px] font-mono">Endpoint: /api/health</p>
            <p className="text-slate-500 text-[11px]">{backendResult?.message}</p>
          </div>

          <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-white">YOLOv8 AI Inference</span>
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                aiResult?.status === 'Online'
                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                  : 'bg-amber-950 text-amber-400 border border-amber-800'
              }`}>
                {testingAi ? 'Checking...' : aiResult?.status || 'Unknown'}
              </span>
            </div>
            <p className="text-slate-400 text-[11px] font-mono">Model: {aiResult?.model || 'Ensemble'}</p>
            <p className="text-slate-500 text-[11px]">{aiResult?.message || `Device: ${aiResult?.device || 'CPU'}`}</p>
          </div>
        </div>
      </div>

      {/* 2. Factory-Level Default PPE Policy */}
      <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2 font-bold text-white text-xs uppercase tracking-wider">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            Factory-Wide Baseline PPE Policy
          </div>
          <span className="text-[11px] text-slate-400">
            {defaultRequiredPpe.length} Mandatory Categories
          </span>
        </div>

        <p className="text-xs text-slate-400">
          Defines the default mandatory PPE equipment required when a camera or worker is outside of calibrated polygon zones. Individual safety zones maintain independent authoritative policies.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
          {AVAILABLE_PPE.map((item) => {
            const isChecked = defaultRequiredPpe.includes(item.id);
            return (
              <label
                key={item.id}
                className={`p-3 rounded-xl border flex items-center gap-3 transition cursor-pointer ${
                  isChecked
                    ? 'bg-emerald-950/40 border-emerald-700/80 text-emerald-200'
                    : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700'
                } ${!isAdmin ? 'opacity-75 cursor-not-allowed' : ''}`}
              >
                <input
                  type="checkbox"
                  checked={isChecked}
                  disabled={!isAdmin}
                  onChange={() => handleTogglePpe(item.id)}
                  className="rounded border-slate-700 text-emerald-600 focus:ring-emerald-500 bg-slate-900"
                />
                <span className="text-xs font-medium">{item.label}</span>
              </label>
            );
          })}
        </div>
      </div>

      {/* 3. Inference, Temporal Confirmation & Auto-Resolution Durations */}
      <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-5">
        <div className="flex items-center gap-2 font-bold text-white text-xs uppercase tracking-wider border-b border-slate-800 pb-3">
          <Sliders className="w-4 h-4 text-sky-400" />
          Inference & Temporal Compliance Parameters
        </div>

        <div className="space-y-5">
          {/* Confidence Threshold */}
          <div>
            <div className="flex justify-between text-xs mb-1">
              <span className="font-semibold text-slate-200">Confidence Threshold</span>
              <span className="font-mono text-sky-400 font-bold">{Math.round(confidenceThreshold * 100)}%</span>
            </div>
            <input
              type="range"
              min="0.2"
              max="0.9"
              step="0.05"
              value={confidenceThreshold}
              disabled={!isAdmin}
              onChange={(e) => setConfidenceThreshold(Number(e.target.value))}
              className="w-full accent-sky-500"
            />
            <p className="text-[11px] text-slate-500 mt-1">
              Detections with confidence scores below this threshold are flagged as UNCERTAIN to prevent false positive violations.
            </p>
          </div>

          {/* Violation Confirmation Duration */}
          <div>
            <div className="flex justify-between text-xs mb-1">
              <span className="font-semibold text-slate-200">Violation Confirmation Duration</span>
              <span className="font-mono text-amber-400 font-bold">{violationConfirmationDurationSec.toFixed(1)} seconds</span>
            </div>
            <input
              type="range"
              min="1.0"
              max="10.0"
              step="0.5"
              value={violationConfirmationDurationSec}
              disabled={!isAdmin}
              onChange={(e) => setViolationConfirmationDurationSec(Number(e.target.value))}
              className="w-full accent-amber-500"
            />
            <p className="text-[11px] text-slate-500 mt-1">
              Missing PPE must persist continuously across this duration before an official Safety Incident is confirmed and persisted.
            </p>
          </div>

          {/* Auto-Resolution Duration */}
          <div>
            <div className="flex justify-between text-xs mb-1">
              <span className="font-semibold text-slate-200">Incident Auto-Resolution Duration</span>
              <span className="font-mono text-emerald-400 font-bold">{incidentAutoResolutionDurationSec.toFixed(1)} seconds</span>
            </div>
            <input
              type="range"
              min="1.0"
              max="10.0"
              step="0.5"
              value={incidentAutoResolutionDurationSec}
              disabled={!isAdmin}
              onChange={(e) => setIncidentAutoResolutionDurationSec(Number(e.target.value))}
              className="w-full accent-emerald-500"
            />
            <p className="text-[11px] text-slate-500 mt-1">
              A previously missing PPE item must be detected continuously across this duration before the open incident is auto-resolved.
            </p>
          </div>

          {/* Video Sampling Interval */}
          <div>
            <div className="flex justify-between text-xs mb-1">
              <span className="font-semibold text-slate-200">Video Frame Sampling Interval</span>
              <span className="font-mono text-sky-400 font-bold">{videoSamplingInterval} ms</span>
            </div>
            <input
              type="range"
              min="300"
              max="2000"
              step="100"
              value={videoSamplingInterval}
              disabled={!isAdmin}
              onChange={(e) => setVideoSamplingInterval(Number(e.target.value))}
              className="w-full accent-sky-500"
            />
            <p className="text-[11px] text-slate-500 mt-1">
              Rate at which video frames are extracted and sent to the inference pipeline to prevent hardware throttling.
            </p>
          </div>

          {/* Alert Cooldown */}
          <div>
            <div className="flex justify-between text-xs mb-1">
              <span className="font-semibold text-slate-200">Violation Alert Cooldown</span>
              <span className="font-mono text-sky-400 font-bold">{alertCooldown} seconds</span>
            </div>
            <input
              type="range"
              min="1"
              max="30"
              step="1"
              value={alertCooldown}
              disabled={!isAdmin}
              onChange={(e) => setAlertCooldown(Number(e.target.value))}
              className="w-full accent-sky-500"
            />
            <p className="text-[11px] text-slate-500 mt-1">
              Suppresses repetitive real-time notification alerts for the same worker within this window.
            </p>
          </div>
        </div>
      </div>

      {/* 4. Camera Health Management Parameters */}
      <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-5">
        <div className="flex items-center gap-2 font-bold text-white text-xs uppercase tracking-wider border-b border-slate-800 pb-3">
          <Activity className="w-4 h-4 text-rose-400" />
          Camera Health & Telemetry Thresholds
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
            <span className="font-semibold text-white text-xs block">WARNING Timeout</span>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min="1"
                max="60"
                step="0.5"
                value={cameraWarningTimeoutSec}
                disabled={!isAdmin}
                onChange={(e) => setCameraWarningTimeoutSec(Number(e.target.value))}
                className="w-full px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-white font-mono text-xs"
              />
              <span className="text-xs text-slate-400">sec</span>
            </div>
            <p className="text-[11px] text-slate-500">No frames received for this duration triggers WARNING state.</p>
          </div>

          <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
            <span className="font-semibold text-white text-xs block">OFFLINE Timeout</span>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min="2"
                max="120"
                step="0.5"
                value={cameraOfflineTimeoutSec}
                disabled={!isAdmin}
                onChange={(e) => setCameraOfflineTimeoutSec(Number(e.target.value))}
                className="w-full px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-white font-mono text-xs"
              />
              <span className="text-xs text-slate-400">sec</span>
            </div>
            <p className="text-[11px] text-slate-500">No frames received for this duration transitions camera to OFFLINE.</p>
          </div>

          <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
            <span className="font-semibold text-white text-xs block">DEGRADED Failures</span>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min="1"
                max="10"
                step="1"
                value={cameraDegradedFailures}
                disabled={!isAdmin}
                onChange={(e) => setCameraDegradedFailures(Number(e.target.value))}
                className="w-full px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-white font-mono text-xs"
              />
              <span className="text-xs text-slate-400">fails</span>
            </div>
            <p className="text-[11px] text-slate-500">Consecutive frame decode or processing failures before marking DEGRADED.</p>
          </div>
        </div>
      </div>

      {/* 5. Audio & Audible Floor Buzzer Preferences */}
      <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-4">
        <div className="flex items-center gap-2 font-bold text-white text-xs uppercase tracking-wider border-b border-slate-800 pb-3">
          <Volume2 className="w-4 h-4 text-emerald-400" />
          Factory Sound & Audible Buzzer Preferences
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <label className={`p-4 rounded-xl border flex items-center justify-between cursor-pointer transition ${
            floorBuzzerEnabled
              ? 'bg-emerald-950/40 border-emerald-700 text-emerald-200'
              : 'bg-slate-950 border-slate-800 text-slate-400'
          } ${!isAdmin ? 'opacity-75 cursor-not-allowed' : ''}`}>
            <div>
              <span className="text-xs font-semibold block text-white">Floor Buzzer Sound</span>
              <span className="text-[11px] text-slate-400">Enable automated local floor buzzer on confirmed violation</span>
            </div>
            <input
              type="checkbox"
              checked={floorBuzzerEnabled}
              disabled={!isAdmin}
              onChange={(e) => setFloorBuzzerEnabled(e.target.checked)}
              className="rounded border-slate-700 text-emerald-600 focus:ring-emerald-500 bg-slate-900 h-4 w-4"
            />
          </label>

          <label className={`p-4 rounded-xl border flex items-center justify-between cursor-pointer transition ${
            soundEnabled
              ? 'bg-emerald-950/40 border-emerald-700 text-emerald-200'
              : 'bg-slate-950 border-slate-800 text-slate-400'
          } ${!isAdmin ? 'opacity-75 cursor-not-allowed' : ''}`}>
            <div>
              <span className="text-xs font-semibold block text-white">Browser Audio Alerts</span>
              <span className="text-[11px] text-slate-400">Play web-audio industrial synthesizer chime in monitoring HUD</span>
            </div>
            <input
              type="checkbox"
              checked={soundEnabled}
              disabled={!isAdmin}
              onChange={(e) => setSoundEnabled(e.target.checked)}
              className="rounded border-slate-700 text-emerald-600 focus:ring-emerald-500 bg-slate-900 h-4 w-4"
            />
          </label>
        </div>
      </div>

      {/* Save Action Bar */}
      {isAdmin && (
        <div className="pt-2 flex justify-end">
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-bold shadow-lg shadow-sky-600/30 transition disabled:opacity-50"
          >
            <Save className={`w-4 h-4 ${saving ? 'animate-spin' : ''}`} />
            <span>{saving ? 'Persisting Configuration...' : 'Save System Settings'}</span>
          </button>
        </div>
      )}
    </div>
  );
}
