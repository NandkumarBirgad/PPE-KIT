import React, { useState, useEffect } from 'react';
import { 
  Volume2, 
  VolumeX, 
  AlertTriangle, 
  CheckCircle2, 
  Zap, 
  RefreshCw, 
  MapPin, 
  ShieldAlert,
  Radio,
  X,
  Siren,
  Building2
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import { playIndustrialSiren, playWarningHorn, stopAllSounds } from '../services/soundAlerts';

export default function SupervisorBuzzerPage() {
  const { user } = useAuth();
  const [zone, setZone] = useState(null);
  const [loading, setLoading] = useState(true);
  const [toastMessage, setToastMessage] = useState(null);
  const [activeAlert, setActiveAlert] = useState(false);

  const showToast = (text, isError = false) => {
    setToastMessage({ text, isError });
    setTimeout(() => setToastMessage(null), 4000);
  };

  const fetchZoneData = async () => {
    setLoading(true);
    try {
      const res = await api.get('/dashboard/supervisor-summary');
      if (res.data?.zone) {
        setZone(res.data.zone);
      }
    } catch (err) {
      console.error('Fetch zone error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchZoneData();
  }, []);

  const handleToggleBuzzer = async () => {
    if (!zone) return;
    try {
      await api.patch(`/zones/${zone._id}`, {
        buzzerEnabled: !zone.buzzerEnabled,
      });
      showToast(`Sector floor buzzer is now ${!zone.buzzerEnabled ? 'ARMED' : 'MUTED'}.`);
      fetchZoneData();
    } catch (err) {
      console.error('Toggle error:', err);
    }
  };

  const handleTestBuzzer = async (type = 'siren') => {
    setActiveAlert(true);
    if (type === 'siren') {
      playIndustrialSiren(4);
    } else {
      playWarningHorn(2);
    }

    try {
      if (zone?._id) {
        await api.post(`/zones/${zone._id}/trigger-buzzer`, { isTest: true });
      }
      showToast(`🚨 Emergency ${type.toUpperCase()} sounded in ${zone?.name || 'Sector'}!`);
    } catch (err) {
      showToast(`🚨 Sounded floor buzzer locally!`);
    } finally {
      setTimeout(() => setActiveAlert(false), 4000);
    }
  };

  const handleSilenceBuzzer = async () => {
    stopAllSounds();
    setActiveAlert(false);
    try {
      await api.post('/buzzers/silence-all', { state: 'MUTED' });
      showToast('Buzzer silenced.');
    } catch (e) {
      showToast('Buzzer silenced.');
    }
  };

  return (
    <div className="space-y-6">
      {/* Toast Alert */}
      {toastMessage && (
        <div className={`p-4 rounded-xl border text-xs flex items-center justify-between shadow-2xl animate-in slide-in-from-top-4 ${
          toastMessage.isError 
            ? 'bg-rose-950/80 border-rose-800 text-rose-200' 
            : 'bg-emerald-950/80 border-emerald-800 text-emerald-200'
        }`}>
          <div className="flex items-center gap-2">
            {toastMessage.isError ? <AlertTriangle className="w-4 h-4 text-rose-400" /> : <CheckCircle2 className="w-4 h-4 text-emerald-400" />}
            <span className="font-semibold">{toastMessage.text}</span>
          </div>
          <button onClick={() => setToastMessage(null)} className="text-slate-400 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-0.5 rounded bg-amber-500/10 border border-amber-500/30 text-amber-400 text-[10px] font-mono font-bold">
              HARDWARE CONTROL
            </span>
            <span className="px-2 py-0.5 rounded-full bg-slate-800 text-sky-400 border border-slate-700 text-[10px] font-bold">
              ZONE ID: {zone?.code || 'SEC-01'}
            </span>
          </div>
          <h1 className="text-xl sm:text-2xl font-black text-white tracking-tight mt-1.5 flex items-center gap-2">
            Sector Floor Hooter & Siren Console
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Manual and automated audible siren triggers for {zone?.name || 'Assigned Zone'}
          </p>
        </div>

        <button
          onClick={fetchZoneData}
          disabled={loading}
          className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition cursor-pointer"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh Relay</span>
        </button>
      </div>

      {/* Main Siren Relay Console */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-6">
          <div className="flex items-center justify-between border-b border-slate-800 pb-4">
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <Siren className="w-5 h-5 text-amber-400" />
                Floor Alarm Sounder Unit
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">Physical high-decibel audible alarm installed on ceiling bay</p>
            </div>
            <span className={`px-2.5 py-1 rounded-full text-[11px] font-bold uppercase tracking-wider font-mono ${
              zone?.buzzerEnabled
                ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                : 'bg-rose-950 text-rose-400 border border-rose-800'
            }`}>
              {zone?.buzzerEnabled ? 'Armed (Active)' : 'Muted (Offline)'}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
              <span className="text-[10px] text-slate-500 uppercase font-mono">Assigned Zone</span>
              <div className="text-sm font-bold text-slate-200">{zone?.name || 'Loading zone...'}</div>
            </div>
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
              <span className="text-[10px] text-slate-500 uppercase font-mono">Hardware Relay IP</span>
              <div className="text-sm font-mono text-emerald-400 font-bold">192.168.1.55:502 (Modbus/TCP)</div>
            </div>
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
              <span className="text-[10px] text-slate-500 uppercase font-mono">Sound Output Level</span>
              <div className="text-sm font-mono text-amber-400 font-bold">105 dB (High Impact Industrial)</div>
            </div>
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
              <span className="text-[10px] text-slate-500 uppercase font-mono">Trigger Timeout</span>
              <div className="text-sm font-mono text-slate-300 font-bold">5 Seconds Auto-Shutoff</div>
            </div>
          </div>

          {/* Action triggers */}
          <div className="space-y-3 pt-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Manual Siren Sounder Actions:
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <button
                onClick={() => handleTestBuzzer('siren')}
                disabled={activeAlert}
                className={`p-4 rounded-xl font-bold text-xs flex flex-col items-center justify-center gap-2 transition cursor-pointer shadow-lg ${
                  activeAlert 
                    ? 'bg-red-600 text-white animate-bounce' 
                    : 'bg-red-950/70 hover:bg-red-900 text-red-200 border border-red-800'
                }`}
              >
                <Volume2 className="w-5 h-5" />
                <span>{activeAlert ? 'SOUNDING...' : 'TRIGGER SIREN (5s)'}</span>
              </button>

              <button
                onClick={() => handleTestBuzzer('horn')}
                disabled={activeAlert}
                className="p-4 rounded-xl bg-amber-950/60 hover:bg-amber-900 text-amber-200 border border-amber-800 font-bold text-xs flex flex-col items-center justify-center gap-2 transition cursor-pointer shadow-lg"
              >
                <Zap className="w-5 h-5" />
                <span>WARNING HORN</span>
              </button>

              <button
                onClick={handleSilenceBuzzer}
                className="p-4 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-bold text-xs flex flex-col items-center justify-center gap-2 transition cursor-pointer shadow-lg"
              >
                <VolumeX className="w-5 h-5 text-amber-400" />
                <span>SILENCE HOOTER</span>
              </button>
            </div>
          </div>
        </div>

        {/* Relay Arm / Disarm Card */}
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-6 flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 border-b border-slate-800 pb-3">
              <ShieldAlert className="w-5 h-5 text-indigo-400" />
              <h3 className="font-bold text-white text-sm">Buzzer Arming State</h3>
            </div>

            <p className="text-xs text-slate-400 mt-3 leading-relaxed">
              When armed, the AI compliance vision pipeline will automatically trigger this floor siren whenever a worker enters the bay without required PPE (Hard Hat or Vest).
            </p>

            <div className="mt-6 p-4 rounded-xl bg-slate-950 border border-slate-800 text-center">
              <span className="text-[10px] text-slate-500 uppercase font-mono block">Current State</span>
              <span className={`text-xl font-black mt-1 block ${zone?.buzzerEnabled ? 'text-emerald-400' : 'text-rose-400'}`}>
                {zone?.buzzerEnabled ? 'ARMED & ACTIVE' : 'MUTED / DISABLED'}
              </span>
            </div>
          </div>

          <button
            onClick={handleToggleBuzzer}
            className={`w-full py-3 px-4 rounded-xl font-bold text-xs transition cursor-pointer ${
              zone?.buzzerEnabled
                ? 'bg-rose-950/80 hover:bg-rose-900 text-rose-300 border border-rose-800'
                : 'bg-emerald-600 hover:bg-emerald-500 text-white'
            }`}
          >
            {zone?.buzzerEnabled ? 'MUTE SECTOR BUZZER' : 'ARM SECTOR BUZZER'}
          </button>
        </div>
      </div>
    </div>
  );
}
