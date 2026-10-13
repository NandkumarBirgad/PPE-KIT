import React, { useState, useEffect } from 'react';
import { 
  Volume2, 
  VolumeX, 
  Bell, 
  AlertTriangle, 
  CheckCircle2, 
  ShieldAlert, 
  Zap, 
  RefreshCw, 
  MapPin, 
  UserCheck, 
  Radio,
  Sliders,
  X
} from 'lucide-react';
import api from '../services/api';
import { playIndustrialSiren, playWarningHorn, stopAllSounds } from '../services/soundAlerts';

export default function BuzzerManagementPage() {
  const [buzzers, setBuzzers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [toastMessage, setToastMessage] = useState(null);
  const [silencingAll, setSilencingAll] = useState(false);

  const showToast = (text, isError = false) => {
    setToastMessage({ text, isError });
    setTimeout(() => setToastMessage(null), 4000);
  };

  const fetchBuzzers = async () => {
    setLoading(true);
    try {
      const res = await api.get('/buzzers');
      setBuzzers(res.data || []);
    } catch (err) {
      console.error('Fetch buzzers error:', err);
    } finally {
      setLoading(false);
    }
  };


  useEffect(() => {
    fetchBuzzers();
  }, []);

  const handleToggleBuzzer = async (buzzer) => {
    try {
      await api.patch(`/zones/${buzzer.zoneId}`, {
        buzzerEnabled: !buzzer.buzzerEnabled,
      });
      showToast(`Buzzer for ${buzzer.zoneName} ${!buzzer.buzzerEnabled ? 'Armed' : 'Silenced'}.`);
      fetchBuzzers();
    } catch (err) {
      console.error('Toggle buzzer error:', err);
    }
  };

  const handleTriggerAlarm = async (buzzer) => {
    if (buzzer.buzzerSound === 'horn') {
      playWarningHorn(2);
    } else {
      playIndustrialSiren(3);
    }
    try {
      await api.post(`/zones/${buzzer.zoneId}/trigger-buzzer`, { isTest: true });
      showToast(`🚨 Triggered floor buzzer for ${buzzer.zoneName}!`);
    } catch (err) {
      showToast(`🚨 Sounded local buzzer alarm for ${buzzer.zoneName}!`);
    }
  };

  const handleSilenceAll = async () => {
    if (!window.confirm('Are you sure you want to silence all active floor buzzers across all facility zones?')) return;
    setSilencingAll(true);
    stopAllSounds();
    try {
      await api.post('/buzzers/silence-all');
      showToast('All facility floor buzzers have been silenced.');
      fetchBuzzers();
    } catch (err) {
      console.error('Silence all error:', err);
    } finally {
      setSilencingAll(false);
    }
  };

  const armedCount = buzzers.filter((b) => b.buzzerEnabled).length;
  const silencedCount = buzzers.length - armedCount;

  return (
    <div className="space-y-6">
      {/* Toast Alert */}
      {toastMessage && (
        <div className={`p-4 rounded-xl border text-xs flex items-center justify-between shadow-2xl animate-in slide-in-from-top-4 ${
          toastMessage.isError 
            ? 'bg-rose-950/80 border-rose-800 text-rose-200' 
            : 'bg-emerald-950/80 border-emerald-700 text-emerald-200'
        }`}>
          <div className="flex items-center gap-2 font-medium">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
            <span>{toastMessage.text}</span>
          </div>
          <button onClick={() => setToastMessage(null)} className="text-slate-400 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl lg:text-2xl font-bold text-white tracking-tight">Floor Buzzer & Siren Command Console</h1>
            <span className="px-2 py-0.5 rounded-full bg-rose-950 border border-rose-800 text-rose-300 text-[10px] font-bold">
              Audible Safety Alarm Mesh
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Centralized control over floor audio sirens, sound wave modulation, emergency muting, and zone hazard alerts
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={fetchBuzzers}
            className="flex items-center gap-2 px-3.5 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-200 text-xs font-semibold border border-slate-700 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Sync Buzzers</span>
          </button>
          <button
            onClick={handleSilenceAll}
            disabled={silencingAll}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold shadow-lg shadow-rose-600/30 transition disabled:opacity-50"
          >
            <VolumeX className="w-4 h-4" />
            <span>Silence All Floor Buzzers</span>
          </button>
        </div>
      </div>

      {/* Buzzer Health Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl flex items-center justify-between">
          <div>
            <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block">Armed Floor Sirens</span>
            <div className="text-3xl font-black text-rose-400 mt-1">{armedCount}</div>
            <span className="text-[10px] text-emerald-400 font-medium">Automatic Violation Trigger Active</span>
          </div>
          <div className="p-3 rounded-xl bg-rose-950/80 border border-rose-800 text-rose-400">
            <Volume2 className="w-6 h-6 animate-pulse" />
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl flex items-center justify-between">
          <div>
            <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block">Silenced / Standby</span>
            <div className="text-3xl font-black text-slate-300 mt-1">{silencedCount}</div>
            <span className="text-[10px] text-slate-500">Muted or Manual Only</span>
          </div>
          <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-slate-500">
            <VolumeX className="w-6 h-6" />
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl flex items-center justify-between">
          <div>
            <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block">Total Monitored Zones</span>
            <div className="text-3xl font-black text-sky-400 mt-1">{buzzers.length}</div>
            <span className="text-[10px] text-sky-400 font-medium">Equipped with Floor Alarm Units</span>
          </div>
          <div className="p-3 rounded-xl bg-sky-950 border border-sky-800 text-sky-400">
            <ShieldAlert className="w-6 h-6" />
          </div>
        </div>
      </div>

      {/* Buzzers Grid */}
      {loading ? (
        <div className="py-16 text-center text-slate-400 text-xs">
          <div className="w-6 h-6 border-2 border-sky-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
          Scanning facility buzzer units...
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {buzzers.map((b) => (
            <div
              key={b.zoneId}
              className={`p-5 rounded-2xl border flex flex-col justify-between shadow-xl transition ${
                b.buzzerEnabled
                  ? 'bg-slate-900 border-rose-900/60 shadow-rose-950/20'
                  : 'bg-slate-950/80 border-slate-800 opacity-70'
              }`}
            >
              <div>
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2.5">
                    <div className={`w-9 h-9 rounded-xl flex items-center justify-center font-bold text-xs ${
                      b.buzzerEnabled
                        ? 'bg-rose-950 border border-rose-800 text-rose-400'
                        : 'bg-slate-800 text-slate-500'
                    }`}>
                      {b.buzzerEnabled ? <Volume2 className="w-4 h-4 animate-pulse" /> : <VolumeX className="w-4 h-4" />}
                    </div>
                    <div>
                      <h3 className="font-bold text-white text-sm">{b.zoneName}</h3>
                      <span className="text-[10px] text-slate-400 font-mono mt-0.5 block">{b.zoneCode}</span>
                    </div>
                  </div>

                  <button
                    onClick={() => handleToggleBuzzer(b)}
                    className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase transition ${
                      b.buzzerEnabled
                        ? 'bg-rose-950 text-rose-300 border border-rose-800'
                        : 'bg-slate-800 text-slate-400 border border-slate-700'
                    }`}
                  >
                    {b.buzzerEnabled ? 'ARMED' : 'MUTED'}
                  </button>
                </div>

                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80 mb-4 space-y-2 text-xs">
                  <div className="flex items-center justify-between text-slate-400">
                    <span className="text-[10px] font-semibold uppercase tracking-wider flex items-center gap-1">
                      <Radio className="w-3 h-3 text-sky-400" /> Sound Type:
                    </span>
                    <span className="text-rose-300 font-bold uppercase">{b.buzzerSound || 'Siren'}</span>
                  </div>

                  <div className="flex items-center justify-between text-slate-400">
                    <span className="text-[10px] font-semibold uppercase tracking-wider flex items-center gap-1">
                      <UserCheck className="w-3 h-3 text-emerald-400" /> Sector Lead:
                    </span>
                    <span className="text-slate-200">{b.supervisor?.name || 'Assigned Lead'}</span>
                  </div>

                  <div className="text-[10px] text-slate-500 pt-1 border-t border-slate-800 flex items-center justify-between">
                    <span>Decibel Rating: 110 dB Floor Horn</span>
                    <span className={b.buzzerEnabled ? 'text-rose-400 font-bold' : 'text-slate-500'}>
                      ● {b.buzzerEnabled ? 'Auto-Trigger' : 'Muted'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="pt-3 border-t border-slate-800 flex items-center justify-between gap-2">
                <button
                  onClick={() => handleTriggerAlarm(b)}
                  className="flex-1 py-1.5 px-3 rounded-lg bg-rose-950 hover:bg-rose-900 border border-rose-800 text-rose-200 text-xs font-bold flex items-center justify-center gap-1.5 transition"
                >
                  <Zap className="w-3.5 h-3.5 text-rose-400" />
                  <span>Test Alarm Sound</span>
                </button>

                <button
                  onClick={() => handleToggleBuzzer(b)}
                  className={`p-2 rounded-lg border text-xs transition ${
                    b.buzzerEnabled
                      ? 'bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700'
                      : 'bg-emerald-950 hover:bg-emerald-900 text-emerald-300 border-emerald-800'
                  }`}
                  title={b.buzzerEnabled ? 'Mute buzzer' : 'Arm buzzer'}
                >
                  {b.buzzerEnabled ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
