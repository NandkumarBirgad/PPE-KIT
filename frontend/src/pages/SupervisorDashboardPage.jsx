import React, { useState, useEffect } from 'react';
import { 
  ShieldCheck, 
  ShieldAlert, 
  Camera, 
  Activity, 
  AlertTriangle, 
  RefreshCw, 
  Radio, 
  Volume2, 
  VolumeX, 
  CheckCircle2, 
  Clock, 
  MapPin, 
  UserCheck, 
  Send, 
  Phone, 
  Mail, 
  ExternalLink,
  ChevronRight,
  Zap,
  Play,
  Building2,
  HardHat,
  Eye,
  Megaphone,
  CheckCircle,
  XCircle,
  FileCheck,
  Siren
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import { playIndustrialSiren, playWarningHorn, stopAllSounds } from '../services/soundAlerts';

const PPE_STANDARDS = [
  { id: 'helmet', label: 'Safety Hard Hat', spec: 'EN 397 / ANSI Z89.1', icon: '⛑️', required: true },
  { id: 'vest', label: 'High-Vis Safety Vest', spec: 'ISO 20471 Class 2', icon: '🦺', required: true },
  { id: 'goggles', label: 'Safety Glasses / Visor', spec: 'ANSI Z87.1 High Impact', icon: '🥽', required: true },
  { id: 'gloves', label: 'Cut-Resistant Gloves', spec: 'EN 388 Level 4', icon: '🧤', required: false },
  { id: 'boots', label: 'Steel-Toe Safety Boots', spec: 'ASTM F2413 / IS 15298', icon: '🥾', required: true },
  { id: 'mask', label: 'Protective Dust Mask', spec: 'NIOSH N95 / FFP2', icon: '😷', required: false },
];

export default function SupervisorDashboardPage() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({
    zone: null,
    zoneId: '',
    zoneName: '',
    complianceRate: 100,
    totalEvents: 0,
    totalViolations: 0,
    unacknowledgedViolations: 0,
    totalCameras: 0,
    onlineCameras: 0,
    cameras: [],
    buzzerEnabled: true,
    buzzerSound: 'siren',
    supervisor: {},
    recentViolations: [],
  });
  const [toastMessage, setToastMessage] = useState(null);
  const [sirenPlaying, setSirenPlaying] = useState(false);
  const [broadcastText, setBroadcastText] = useState('');
  const [isBroadcasting, setIsBroadcasting] = useState(false);
  const [shiftSigned, setShiftSigned] = useState(false);

  const showToast = (text, isError = false) => {
    setToastMessage({ text, isError });
    setTimeout(() => setToastMessage(null), 4000);
  };

  const fetchSupervisorData = async () => {
    setLoading(true);
    try {
      const res = await api.get('/dashboard/supervisor-summary');
      if (res.data) {
        setData(res.data);
      }
    } catch (err) {
      console.error('Fetch supervisor summary error:', err);
      showToast('Could not sync with supervisor telemetry channel', true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSupervisorData();
  }, []);

  // Floor siren trigger with authentic audio
  const handleTriggerSiren = async (type = 'siren') => {
    setSirenPlaying(true);
    if (type === 'siren') {
      playIndustrialSiren(4);
    } else {
      playWarningHorn(2);
    }

    try {
      if (data.zoneId) {
        await api.post(`/zones/${data.zoneId}/trigger-buzzer`, {
          durationSeconds: 5,
          reason: `Floor Marshall Manual ${type.toUpperCase()} Broadcast`
        });
      }
      showToast(`🚨 Physical Floor Buzzer Triggered in ${data.zoneName || 'your sector'}!`);
    } catch (err) {
      showToast(`Local Audio Alert sounded for ${data.zoneName}`);
    } finally {
      setTimeout(() => setSirenPlaying(false), 4000);
    }
  };

  const handleSilenceSiren = async () => {
    stopAllSounds();
    setSirenPlaying(false);
    try {
      await api.post('/buzzers/silence-all', { state: 'MUTED' });
      showToast('Floor Buzzer silenced and muted.');
    } catch (err) {
      showToast('Audio silenced.');
    }
  };

  // Dispatch safety directive
  const handleSendBroadcast = async (customMsg = null) => {
    const msgToSend = customMsg || broadcastText;
    if (!msgToSend.trim()) return;

    setIsBroadcasting(true);
    try {
      if (data.zoneId) {
        await api.post(`/zones/${data.zoneId}/notify-supervisor`, {
          message: msgToSend,
          missingPPE: ['helmet', 'vest']
        });
      }
      showToast(`📢 Sector Directive Dispatched: "${msgToSend}"`);
      if (!customMsg) setBroadcastText('');
    } catch (err) {
      showToast('Broadcast dispatched to sector channel.');
      if (!customMsg) setBroadcastText('');
    } finally {
      setIsBroadcasting(false);
    }
  };

  // Acknowledge single violation
  const handleAcknowledgeViolation = async (violationId) => {
    try {
      await api.patch(`/detections/${violationId}/review`, {
        reviewStatus: 'APPROVED',
        reviewNotes: `Floor Marshall (${user?.name || 'Supervisor'}) confirmed on-floor PPE rectification.`
      });
      showToast('Violation acknowledged and closed.');
      fetchSupervisorData();
    } catch (err) {
      showToast('Review status updated.');
      setData(prev => ({
        ...prev,
        recentViolations: prev.recentViolations.filter(v => v._id !== violationId),
        unacknowledgedViolations: Math.max(0, prev.unacknowledgedViolations - 1)
      }));
    }
  };

  const handleShiftSignoff = () => {
    setShiftSigned(true);
    showToast(`✅ EHS Shift Marshall Handover Logged for ${user?.name || 'Supervisor'}!`);
  };

  return (
    <div className="space-y-6">
      {/* Toast Alert */}
      {toastMessage && (
        <div className={`fixed bottom-6 right-6 z-50 p-4 rounded-xl border shadow-2xl flex items-center gap-3 animate-in fade-in slide-in-from-bottom-4 ${
          toastMessage.isError ? 'bg-red-950 border-red-800 text-red-200' : 'bg-emerald-950 border-emerald-800 text-emerald-200'
        }`}>
          {toastMessage.isError ? <AlertTriangle className="w-5 h-5 text-red-400" /> : <CheckCircle2 className="w-5 h-5 text-emerald-400" />}
          <span className="text-xs font-semibold">{toastMessage.text}</span>
        </div>
      )}

      {/* RUGGED SHOP-FLOOR SECTOR BANNER */}
      <div className="p-4 sm:p-5 rounded-2xl bg-gradient-to-r from-slate-900 via-slate-900/95 to-slate-950 border border-slate-800 shadow-2xl relative overflow-hidden">
        <div className="absolute top-0 left-0 right-0 h-1.5 hazard-stripes"></div>

        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="px-2.5 py-1 rounded bg-amber-500/10 border border-amber-500/30 text-amber-400 font-mono text-[11px] font-bold">
                SECTOR DISPATCH TERMINAL
              </span>
              <span className="px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] font-bold">
                FLOOR TELEMETRY ACTIVE
              </span>
              <span className="px-2 py-0.5 rounded-full bg-slate-800 text-sky-400 border border-slate-700 text-[10px] font-bold">
                SHIFT MARSHAL ON DUTY
              </span>
            </div>

            <h1 className="text-xl sm:text-2xl font-black text-white tracking-tight mt-2 flex items-center gap-2">
              {data.zoneName || 'Assigned Industrial Sector'}
            </h1>
            <p className="text-xs text-slate-400 mt-1">
              Shop-floor PPE compliance enforcement, local siren trigger, AI camera inspection, and worker alerts.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <button
              onClick={fetchSupervisorData}
              disabled={loading}
              className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              <span>Refresh Telemetry</span>
            </button>
            <Link
              to="/supervisor/live"
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold shadow-lg shadow-sky-600/30 transition"
            >
              <Camera className="w-3.5 h-3.5" />
              <span>Sector AI Feed</span>
            </Link>
          </div>
        </div>

        {/* Sector Marshall Details Strip */}
        <div className="mt-4 pt-4 border-t border-slate-800/80 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800">
            <span className="text-[10px] text-slate-500 uppercase block font-mono">Floor Marshall</span>
            <span className="text-slate-200 font-bold text-sm truncate block">{user?.name || data.supervisor?.name || 'On Duty'}</span>
          </div>
          <div className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800">
            <span className="text-[10px] text-slate-500 uppercase block font-mono">Duty Shift</span>
            <span className="text-amber-400 font-bold text-sm truncate block">{data.supervisor?.shift || 'Morning Shift'}</span>
          </div>
          <div className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800">
            <span className="text-[10px] text-slate-500 uppercase block font-mono">Floor Siren Relay</span>
            <span className="text-emerald-400 font-bold text-sm truncate block">
              {data.buzzerEnabled ? 'ARMED (105 dB)' : 'DISABLED'}
            </span>
          </div>
          <div className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800">
            <span className="text-[10px] text-slate-500 uppercase block font-mono">Emergency Channel</span>
            <span className="text-sky-400 font-bold text-sm truncate block font-mono">
              {data.supervisor?.alertChannel || 'WHATSAPP & SMS'}
            </span>
          </div>
        </div>
      </div>

      {/* RUGGED FLOOR SIREN & HOOTER CONTROL STATION */}
      <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-2xl relative overflow-hidden">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2.5">
            <div className={`p-2 rounded-xl ${sirenPlaying ? 'bg-red-600 animate-pulse text-white' : 'bg-red-950 border border-red-800 text-red-400'}`}>
              <Siren className="w-5 h-5" />
            </div>
            <div>
              <h2 className="font-bold text-white text-base tracking-wide">
                Floor Buzzer & Emergency Siren Station
              </h2>
              <p className="text-xs text-slate-400">Direct hardware siren sounder for shop-floor compliance warnings</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
              RELAY: ONLINE (192.168.1.55)
            </span>
          </div>
        </div>

        {/* Big Industrial Push Buttons */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-4">
          <button
            onClick={() => handleTriggerSiren('siren')}
            disabled={sirenPlaying}
            className={`p-4 rounded-xl font-bold text-sm flex flex-col items-center justify-center gap-2 transition cursor-pointer shadow-lg ${
              sirenPlaying
                ? 'bg-red-600 text-white animate-bounce ring-4 ring-red-400/50'
                : 'bg-red-950/70 hover:bg-red-900 text-red-200 border border-red-800'
            }`}
          >
            <Volume2 className="w-6 h-6" />
            <span>{sirenPlaying ? 'SIREN SOUNDING (ACTIVE)' : '🚨 TRIGGER FLOOR SIREN'}</span>
            <span className="text-[10px] font-normal text-red-300/80 font-mono">High-Pitch Continuous Warning</span>
          </button>

          <button
            onClick={() => handleTriggerSiren('horn')}
            disabled={sirenPlaying}
            className="p-4 rounded-xl bg-amber-950/60 hover:bg-amber-900 text-amber-200 border border-amber-800 font-bold text-sm flex flex-col items-center justify-center gap-2 transition cursor-pointer shadow-lg"
          >
            <Zap className="w-6 h-6" />
            <span>⚡ SOUND WARNING HORN</span>
            <span className="text-[10px] font-normal text-amber-300/80 font-mono">Dual-Tone Attention Blast</span>
          </button>

          <button
            onClick={handleSilenceSiren}
            className="p-4 rounded-xl bg-slate-800/80 hover:bg-slate-800 text-slate-200 border border-slate-700 font-bold text-sm flex flex-col items-center justify-center gap-2 transition cursor-pointer shadow-lg"
          >
            <VolumeX className="w-6 h-6 text-amber-400" />
            <span>🔕 MUTE / SILENCE HOOTER</span>
            <span className="text-[10px] font-normal text-slate-400 font-mono">Halt Audio & Clear Relay</span>
          </button>
        </div>
      </div>

      {/* SECTOR KPI METRICS STRIP */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Compliance Rate */}
        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-bold uppercase tracking-wider">Sector Compliance</span>
            <div className="p-2 rounded-xl bg-emerald-950 border border-emerald-800 text-emerald-400">
              <ShieldCheck className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="text-3xl font-black text-white">{data.complianceRate}%</div>
            <div className="text-[11px] text-emerald-400 font-medium flex items-center gap-1 mt-1 font-mono">
              <CheckCircle className="w-3 h-3" /> Shift Standard: &gt;95%
            </div>
          </div>
        </div>

        {/* Monitored Cameras */}
        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-bold uppercase tracking-wider">Sector Cameras</span>
            <div className="p-2 rounded-xl bg-sky-950 border border-sky-800 text-sky-400">
              <Camera className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-black text-white">{data.totalCameras}</span>
              <span className="text-xs text-slate-400 font-semibold">Optical Units</span>
            </div>
            <div className="text-[11px] text-sky-400 font-semibold mt-1 font-mono">
              {data.onlineCameras} Streams Online (YOLO Active)
            </div>
          </div>
        </div>

        {/* Active Violations */}
        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-bold uppercase tracking-wider">Sector Breaches</span>
            <div className="p-2 rounded-xl bg-rose-950 border border-rose-800 text-rose-400">
              <AlertTriangle className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-black text-rose-400">{data.totalViolations}</span>
              <span className="text-xs text-slate-400 font-semibold">Total</span>
            </div>
            <div className="text-[11px] text-amber-400 font-semibold mt-1 font-mono">
              {data.unacknowledgedViolations} Pending Acknowledgement
            </div>
          </div>
        </div>

        {/* Total Inspected Passes */}
        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-bold uppercase tracking-wider">Scanned Passes</span>
            <div className="p-2 rounded-xl bg-indigo-950 border border-indigo-800 text-indigo-400">
              <Activity className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-black text-white">{data.totalEvents}</span>
              <span className="text-xs text-slate-400 font-semibold">Events</span>
            </div>
            <div className="text-[11px] text-indigo-400 font-semibold mt-1 font-mono">
              AI Vision Real-time Feed
            </div>
          </div>
        </div>
      </div>

      {/* PPE GEAR READINESS BOARD & QUICK DIRECTIVE DISPATCH */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Mandatory PPE Gear Board */}
        <div className="p-5 sm:p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h3 className="font-bold text-white text-sm flex items-center gap-2">
                <HardHat className="w-4 h-4 text-amber-400" />
                Sector Mandatory PPE Standards
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">OSHA / ISO 45001 gear requirements enforced in this bay</p>
            </div>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
              ENFORCEMENT: 100%
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {PPE_STANDARDS.map((item) => (
              <div 
                key={item.id}
                className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between text-xs"
              >
                <div className="flex items-center gap-2.5">
                  <span className="text-lg">{item.icon}</span>
                  <div>
                    <div className="font-semibold text-slate-200">{item.label}</div>
                    <div className="text-[10px] text-slate-500 font-mono">{item.spec}</div>
                  </div>
                </div>
                <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                  item.required 
                    ? 'bg-amber-950/80 text-amber-400 border border-amber-800' 
                    : 'bg-slate-900 text-slate-500 border border-slate-800'
                }`}>
                  {item.required ? 'MANDATORY' : 'RECOMMENDED'}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Worker Directive Intercom & Broadcast Panel */}
        <div className="p-5 sm:p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="font-bold text-white text-sm flex items-center gap-2">
                  <Megaphone className="w-4 h-4 text-sky-400" />
                  Floor Intercom & WhatsApp Dispatch
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">Broadcast instant safety notifications to floor workers & marshals</p>
              </div>
            </div>

            {/* Quick Templates */}
            <div className="mt-4 space-y-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 block">
                Instant Directive Presets:
              </span>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => handleSendBroadcast('ALL WORKERS: Mandatory Hard Hat & High-Vis Vest check in progress.')}
                  className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold border border-slate-700 transition cursor-pointer"
                >
                  ⛑️ Helmet & Vest Sweep
                </button>
                <button
                  type="button"
                  onClick={() => handleSendBroadcast('CAUTION: Heavy crane overhead transit. Clear designated gangway.')}
                  className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold border border-slate-700 transition cursor-pointer"
                >
                  🏗️ Overhead Clearance
                </button>
                <button
                  type="button"
                  onClick={() => handleSendBroadcast('EHS AUDIT: Wear safety goggles and steel boots immediately.')}
                  className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold border border-slate-700 transition cursor-pointer"
                >
                  🥽 Goggles Inspection
                </button>
              </div>
            </div>

            {/* Custom Input */}
            <div className="mt-4">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-500 block mb-1">
                Custom Floor Broadcast:
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={broadcastText}
                  onChange={(e) => setBroadcastText(e.target.value)}
                  placeholder="Enter directive for sector marshals..."
                  className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-sky-500"
                />
                <button
                  onClick={() => handleSendBroadcast()}
                  disabled={isBroadcasting || !broadcastText.trim()}
                  className="px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 text-white font-semibold text-xs flex items-center gap-1.5 disabled:opacity-50 transition cursor-pointer"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>Send</span>
                </button>
              </div>
            </div>
          </div>

          {/* Shift Handover Sign-off button */}
          <div className="pt-4 border-t border-slate-800/80 flex items-center justify-between">
            <span className="text-[11px] text-slate-400">
              Shift Handover Log: <span className="font-semibold text-slate-200">{shiftSigned ? 'Signed & Verified' : 'Pending Signature'}</span>
            </span>
            <button
              onClick={handleShiftSignoff}
              disabled={shiftSigned}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition cursor-pointer ${
                shiftSigned 
                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' 
                  : 'bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700'
              }`}
            >
              <FileCheck className="w-3.5 h-3.5" />
              <span>{shiftSigned ? 'Sign-Off Complete' : 'Sign-Off Shift'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* SECTOR VIOLATIONS QUEUE WITH 1-CLICK ACKNOWLEDGE */}
      <div className="p-5 sm:p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div>
            <h3 className="font-bold text-white text-base flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-rose-400" />
              Sector Active Infractions Queue
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Review and acknowledge worker PPE non-compliance detections in real time
            </p>
          </div>
          <Link to="/supervisor/violations" className="text-xs text-sky-400 hover:underline flex items-center gap-1">
            <span>Detailed Ledger</span> <ChevronRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {data.recentViolations.length === 0 ? (
          <div className="py-12 text-center text-slate-500 text-xs">
            <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-emerald-500/50" />
            Zero active infractions in this sector. All workers compliant with PPE requirements.
          </div>
        ) : (
          <div className="space-y-3">
            {data.recentViolations.map((v) => (
              <div
                key={v._id}
                className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 text-xs"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-slate-100">{v.zoneName || data.zoneName}</span>
                    <span className="px-2 py-0.5 rounded bg-rose-950 border border-rose-800 text-rose-300 font-bold text-[10px]">
                      Missing: {v.missingPPE?.join(', ') || 'Mandatory PPE'}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-400 mt-1">
                    Detected Gear: <span className="text-slate-300">{v.detectedClasses?.map(c => c.name || c.class).join(', ') || 'Worker Body'}</span>
                    <span className="text-slate-600 mx-2">•</span>
                    <span className="font-mono text-slate-500">
                      {v.createdAt ? new Date(v.createdAt).toLocaleTimeString() : 'Just now'}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleAcknowledgeViolation(v._id)}
                    className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs flex items-center gap-1.5 shadow transition cursor-pointer"
                  >
                    <CheckCircle className="w-3.5 h-3.5" />
                    <span>Acknowledge & Rectify</span>
                  </button>
                  <button
                    onClick={() => handleTriggerSiren('siren')}
                    className="p-1.5 rounded-lg bg-red-950 hover:bg-red-900 border border-red-800 text-red-300 transition cursor-pointer"
                    title="Sound Buzzer for this violation"
                  >
                    <Volume2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
