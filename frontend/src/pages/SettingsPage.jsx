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
  HelpCircle
} from 'lucide-react';
import api, { AI_BASE_URL } from '../services/api';

export default function SettingsPage() {
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.35);
  const [videoSamplingInterval, setVideoSamplingInterval] = useState(1000);
  const [alertCooldown, setAlertCooldown] = useState(5);
  const [temporalConfirmation, setTemporalConfirmation] = useState(3);

  // Status
  const [testingBackend, setTestingBackend] = useState(false);
  const [backendResult, setBackendResult] = useState(null);
  const [testingAi, setTestingAi] = useState(false);
  const [aiResult, setAiResult] = useState(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Load from local storage
  useEffect(() => {
    const savedConf = localStorage.getItem('ppe_conf_threshold');
    if (savedConf) setConfidenceThreshold(Number(savedConf));

    const savedInterval = localStorage.getItem('ppe_sample_interval');
    if (savedInterval) setVideoSamplingInterval(Number(savedInterval));

    const savedCooldown = localStorage.getItem('ppe_alert_cooldown');
    if (savedCooldown) setAlertCooldown(Number(savedCooldown));

    testServices();
  }, []);

  const testServices = async () => {
    // Backend test
    setTestingBackend(true);
    try {
      const res = await api.get('/health');
      setBackendResult({ status: 'Online', message: res.data.message || 'Node.js Express Server Healthy' });
    } catch (err) {
      setBackendResult({ status: 'Offline', message: err.message || 'Cannot reach API backend' });
    } finally {
      setTestingBackend(false);
    }

    // AI Service test
    setTestingAi(true);
    try {
      const res = await fetch(`${AI_BASE_URL}/health`);
      if (res.ok) {
        const data = await res.json();
        setAiResult({
          status: 'Online',
          model: data.model_path || 'YOLOv8 PPE Model',
          device: data.device || 'CPU',
        });
      } else {
        setAiResult({ status: 'Error', message: 'Inference service reported an error' });
      }
    } catch (err) {
      setAiResult({ status: 'Offline', message: 'Flask AI service is not running on port 5001' });
    } finally {
      setTestingAi(false);
    }
  };

  const handleSave = () => {
    localStorage.setItem('ppe_conf_threshold', confidenceThreshold.toString());
    localStorage.setItem('ppe_sample_interval', videoSamplingInterval.toString());
    localStorage.setItem('ppe_alert_cooldown', alertCooldown.toString());
    setSaveSuccess(true);
    setTimeout(() => setSaveSuccess(false), 3000);
  };

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="text-xl lg:text-2xl font-bold text-white tracking-tight">System Infrastructure Settings</h1>
        <p className="text-xs text-slate-400 mt-1">Configure neural network thresholds, camera throttling, and backend links</p>
      </div>

      {saveSuccess && (
        <div className="p-3 rounded-xl bg-emerald-950/40 border border-emerald-800 text-emerald-300 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>Configuration parameters persisted successfully!</span>
        </div>
      )}

      {/* Connectivity & Health Status */}
      <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2 font-bold text-white text-xs uppercase tracking-wider">
            <Server className="w-4 h-4 text-sky-400" />
            Service Health Checks
          </div>
          <button
            onClick={testServices}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 border border-slate-700 transition"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Re-test Diagnostics
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
          {/* Node.js Backend */}
          <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-white">Node.js Express API</span>
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                backendResult?.status === 'Online'
                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                  : 'bg-rose-950 text-rose-400 border border-rose-800'
              }`}>
                {testingBackend ? 'Checking...' : backendResult?.status || 'Unknown'}
              </span>
            </div>
            <p className="text-slate-400 text-[11px] font-mono">
              URL: {import.meta.env.VITE_API_URL || 'http://localhost:5000/api'}
            </p>
            <p className="text-slate-500 text-[11px]">{backendResult?.message}</p>
          </div>

          {/* Python AI Service */}
          <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-white">Python Flask AI Service</span>
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                aiResult?.status === 'Online'
                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                  : 'bg-amber-950 text-amber-400 border border-amber-800'
              }`}>
                {testingAi ? 'Checking...' : aiResult?.status || 'Unknown'}
              </span>
            </div>
            <p className="text-slate-400 text-[11px] font-mono">
              URL: {AI_BASE_URL}
            </p>
            {aiResult?.model && (
              <p className="text-slate-400 text-[11px]">
                Model: <b className="text-sky-300">{aiResult.model}</b> ({aiResult.device})
              </p>
            )}
            <p className="text-slate-500 text-[11px]">{aiResult?.message}</p>
          </div>
        </div>
      </div>

      {/* AI Detection & Video Parameters */}
      <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 shadow-xl space-y-5">
        <div className="flex items-center gap-2 font-bold text-white text-xs uppercase tracking-wider border-b border-slate-800 pb-3">
          <Sliders className="w-4 h-4 text-sky-400" />
          Inference & Compliance Parameters
        </div>

        <div className="space-y-4">
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
              onChange={(e) => setConfidenceThreshold(Number(e.target.value))}
              className="w-full accent-sky-500"
            />
            <p className="text-[11px] text-slate-500 mt-1">
              Detections with confidence scores below this threshold will be flagged as UNCERTAIN or ignored.
            </p>
          </div>

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
              onChange={(e) => setVideoSamplingInterval(Number(e.target.value))}
              className="w-full accent-sky-500"
            />
            <p className="text-[11px] text-slate-500 mt-1">
              Rate at which video frames are extracted and sent to the inference pipeline to avoid overload.
            </p>
          </div>

          <div>
            <div className="flex justify-between text-xs mb-1">
              <span className="font-semibold text-slate-200">Violation Alert Cooldown</span>
              <span className="font-mono text-sky-400 font-bold">{alertCooldown} seconds</span>
            </div>
            <input
              type="range"
              min="2"
              max="30"
              step="1"
              value={alertCooldown}
              onChange={(e) => setAlertCooldown(Number(e.target.value))}
              className="w-full accent-sky-500"
            />
            <p className="text-[11px] text-slate-500 mt-1">
              Suppresses repetitive real-time notification alerts for the same worker within this window.
            </p>
          </div>

          <div>
            <div className="flex justify-between text-xs mb-1">
              <span className="font-semibold text-slate-200">Temporal Frame Confirmation</span>
              <span className="font-mono text-sky-400 font-bold">{temporalConfirmation} consecutive frames</span>
            </div>
            <input
              type="range"
              min="1"
              max="5"
              step="1"
              value={temporalConfirmation}
              onChange={(e) => setTemporalConfirmation(Number(e.target.value))}
              className="w-full accent-sky-500"
            />
            <p className="text-[11px] text-slate-500 mt-1">
              Requires a violation to persist across consecutive frames before firing a confirmed alert.
            </p>
          </div>
        </div>

        <div className="pt-4 border-t border-slate-800 flex justify-end">
          <button
            onClick={handleSave}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold shadow-lg shadow-sky-600/30 transition"
          >
            <Save className="w-4 h-4" /> Save System Settings
          </button>
        </div>
      </div>
    </div>
  );
}
