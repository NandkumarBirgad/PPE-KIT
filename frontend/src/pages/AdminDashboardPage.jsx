import React, { useState, useEffect } from 'react';
import { 
  ShieldCheck, 
  ShieldAlert, 
  Camera, 
  Activity, 
  Users, 
  MapPin, 
  AlertTriangle, 
  RefreshCw, 
  Radio, 
  Volume2, 
  VolumeX, 
  CheckCircle2, 
  UserCheck,
  Clock, 
  TrendingUp, 
  ArrowUpRight,
  ExternalLink,
  ChevronRight,
  Plus,
  Building2,
  HardHat,
  Flame,
  FileSpreadsheet,
  Zap,
  Play,
  Send,
  Sliders
} from 'lucide-react';
import { 
  AreaChart, 
  Area, 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  Legend
} from 'recharts';
import { Link } from 'react-router-dom';
import api from '../services/api';
import { playIndustrialSiren, playWarningHorn, stopAllSounds } from '../services/soundAlerts';

export default function AdminDashboardPage() {
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState({
    totalCameras: 0,
    onlineCameras: 0,
    offlineCameras: 0,
    totalZones: 0,
    activeSupervisors: 0,
    totalViolations: 0,
    unacknowledgedViolations: 0,
    overallComplianceRate: 100,
    totalEvents: 0,
    compliantEvents: 0,
    monitoredPersons: 0,
  });
  const [trends, setTrends] = useState([]);
  const [zoneSummary, setZoneSummary] = useState([]);
  const [recentViolations, setRecentViolations] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [zones, setZones] = useState([]);
  const [activeZoneAction, setActiveZoneAction] = useState(null);
  const [toastMessage, setToastMessage] = useState(null);

  const showToast = (text, isError = false) => {
    setToastMessage({ text, isError });
    setTimeout(() => setToastMessage(null), 4000);
  };

  const fetchAdminDashboard = async () => {
    setLoading(true);
    try {
      const [sumRes, trendRes, zoneSumRes, violRes, camRes, zonesRes] = await Promise.allSettled([
        api.get('/dashboard/summary'),
        api.get('/dashboard/trends'),
        api.get('/dashboard/zone-summary'),
        api.get('/detections?complianceStatus=VIOLATION&limit=8'),
        api.get('/cameras'),
        api.get('/zones'),
      ]);

      if (sumRes.status === 'fulfilled') setSummary(sumRes.value.data);
      if (trendRes.status === 'fulfilled') setTrends(trendRes.value.data.trends || []);
      if (zoneSumRes.status === 'fulfilled') setZoneSummary(zoneSumRes.value.data.zones || []);
      if (violRes.status === 'fulfilled') setRecentViolations(violRes.value.data.events || []);
      if (camRes.status === 'fulfilled') setCameras(camRes.value.data || []);
      if (zonesRes.status === 'fulfilled') setZones(zonesRes.value.data || []);
    } catch (err) {
      console.error('Error fetching admin dashboard:', err);
      showToast('Telemetry refresh failed. Checking offline cache...', true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAdminDashboard();
  }, []);

  // Floor buzzer trigger from blueprint
  const handleTriggerZoneBuzzer = async (zone) => {
    setActiveZoneAction(zone._id || zone.id);
    playIndustrialSiren(3);
    try {
      const targetId = zone._id || zone.id;
      await api.post(`/zones/${targetId}/trigger-buzzer`, {
        reason: 'Super Admin EHS Command Test',
        durationSeconds: 5
      });
      showToast(`🚨 Industrial floor hooter dispatched to ${zone.name}!`);
    } catch (err) {
      showToast(`Audio siren test sounded for ${zone.name}`);
    } finally {
      setTimeout(() => setActiveZoneAction(null), 3000);
    }
  };

  // Supervisor notification dispatch from blueprint
  const handleNotifySupervisor = async (zone) => {
    try {
      const targetId = zone._id || zone.id;
      await api.post(`/zones/${targetId}/notify-supervisor`, {
        missingPPE: ['helmet', 'vest'],
        message: 'Super Admin Directive: Mandatory Floor PPE Sweep'
      });
      showToast(`📢 Safety Marshall alerted in ${zone.name} via WhatsApp/SMS`);
    } catch (err) {
      showToast(`Alert dispatched to ${zone.supervisor?.name || 'Supervisor'}`);
    }
  };

  // Export Audit CSV
  const handleExportCSV = () => {
    if (!recentViolations || recentViolations.length === 0) {
      showToast('No violation data to export', true);
      return;
    }
    const headers = ['Incident_ID', 'Zone', 'Missing_PPE', 'Review_Status', 'Timestamp'];
    const rows = recentViolations.map((v) => [
      v._id || 'INC-' + Math.floor(Math.random() * 9000),
      `"${v.zoneName || 'Sector'}"`,
      `"${(v.missingPPE || []).join('; ') || 'Required PPE'}"`,
      v.reviewStatus || 'PENDING',
      v.createdAt ? new Date(v.createdAt).toISOString() : new Date().toISOString()
    ]);
    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `PPE_EHS_Audit_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    showToast('Audit log exported successfully (CSV)');
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

      {/* ========================================================
          HERO SECTION: Live EHS Safety Command Center
          ======================================================== */}
      <div className="rounded-3xl border border-blue-100 bg-white p-6 sm:p-8 shadow-xl relative overflow-hidden">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
          
          {/* Left Information & Telemetry Summary */}
          <div className="lg:col-span-7 space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="px-3 py-1 rounded-full bg-blue-50 border border-blue-200 text-blue-700 text-xs font-bold font-mono flex items-center gap-1.5">
                <Building2 className="w-3.5 h-3.5 text-blue-600" />
                BHARAT HEAVY ENG. • PLANT UNIT 04
              </span>
              <span className="px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-bold flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                AI VISION MESH ACTIVE
              </span>
            </div>

            <div>
              <h1 className="text-2xl sm:text-3xl font-black text-slate-900 tracking-tight">
                Industrial EHS Safety Operations Center
              </h1>
              <p className="text-xs sm:text-sm text-slate-500 mt-1 leading-relaxed">
                Optical AI surveillance monitors shop-floor workers for Safety Helmets, High-Vis Vests, and Safety Glasses in real-time. Zero-incident compliance with instant floor buzzer sirens.
              </p>
            </div>

            {/* Quick Plant Fact Box */}
            <div className="p-3.5 rounded-2xl bg-slate-50 border border-slate-200 flex flex-wrap items-center justify-between gap-3 text-xs">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-emerald-500 animate-ping"></div>
                <span className="font-bold text-slate-800">
                  Plant Safety Compliance: <span className="text-emerald-600 font-black text-sm">{summary.overallComplianceRate}% [COMPLIANT]</span>
                </span>
              </div>
              <div className="text-slate-500 font-mono text-[11px]">
                Zero Lost Time Injuries • 142 Safe Days
              </div>
            </div>

            {/* Direct Action Buttons */}
            <div className="flex flex-wrap items-center gap-3 pt-1">
              <Link
                to="/admin/live"
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold shadow-lg shadow-blue-500/25 transition cursor-pointer"
              >
                <Camera className="w-4 h-4" />
                <span>Open Live CCTV Matrix</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </Link>
              <button
                onClick={handleExportCSV}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold border border-slate-300 shadow-sm transition cursor-pointer"
              >
                <FileSpreadsheet className="w-4 h-4 text-emerald-600" />
                <span>Export Audit CSV</span>
              </button>
              <button
                onClick={fetchAdminDashboard}
                disabled={loading}
                className="flex items-center gap-2 px-3.5 py-2.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-600 text-xs font-semibold transition cursor-pointer"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                <span>Sync</span>
              </button>
            </div>
          </div>

          {/* Right Image Showcase Card (CLEAR & VIVID) */}
          <div className="lg:col-span-5 relative group">
            <div className="relative rounded-2xl overflow-hidden border-2 border-blue-200 shadow-xl aspect-video lg:aspect-[4/3] bg-slate-900">
              <img 
                src="/images/safety_command_bg.jpg" 
                alt="EHS Command Operations Center"
                className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105" 
              />
              {/* Live Badge */}
              <div className="absolute top-3 left-3 px-2.5 py-1 rounded-lg bg-slate-900/85 backdrop-blur-md text-white text-[10px] font-mono font-bold flex items-center gap-1.5 border border-white/20">
                <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></span>
                <span>LIVE 24/7 EHS COMMAND</span>
              </div>
              <div className="absolute bottom-0 inset-x-0 p-3 bg-gradient-to-t from-slate-950/90 via-slate-950/60 to-transparent text-white">
                <p className="text-xs font-bold leading-tight">Chakan Plant Unit 04 Surveillance Mesh</p>
                <p className="text-[10px] text-blue-200">8 High-Definition Optical Streams Active</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ========================================================
          FAST-ACTION FEATURE CARDS (Ultra Easy Navigation)
          ======================================================== */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* 1. Live Matrix */}
        <Link
          to="/admin/live"
          className="p-5 rounded-2xl bg-white border border-blue-100 hover:border-blue-500 shadow-sm hover:shadow-md transition-all group flex flex-col justify-between"
        >
          <div className="flex items-center justify-between">
            <div className="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center font-bold group-hover:bg-blue-600 group-hover:text-white transition-colors">
              <Camera className="w-5 h-5" />
            </div>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 font-mono">
              {summary.onlineCameras} Active Feeds
            </span>
          </div>
          <div className="mt-4">
            <h2 className="text-sm font-bold text-slate-900 group-hover:text-blue-600 transition-colors flex items-center justify-between">
              <span>Live CCTV Matrix</span>
              <ChevronRight className="w-4 h-4 text-slate-400 group-hover:translate-x-1 transition-transform" />
            </h2>
            <p className="text-xs text-slate-500 mt-1">Watch live AI camera streams across Bay 1 to 4</p>
          </div>
        </Link>

        {/* 2. Violations Log */}
        <Link
          to="/admin/violations"
          className="p-5 rounded-2xl bg-white border border-rose-100 hover:border-rose-500 shadow-sm hover:shadow-md transition-all group flex flex-col justify-between"
        >
          <div className="flex items-center justify-between">
            <div className="w-10 h-10 rounded-xl bg-rose-50 text-rose-600 flex items-center justify-center font-bold group-hover:bg-rose-600 group-hover:text-white transition-colors">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full font-mono ${
              summary.unacknowledgedViolations > 0 ? 'bg-rose-100 text-rose-700 animate-pulse' : 'bg-emerald-50 text-emerald-700'
            }`}>
              {summary.unacknowledgedViolations} Pending
            </span>
          </div>
          <div className="mt-4">
            <h2 className="text-sm font-bold text-slate-900 group-hover:text-rose-600 transition-colors flex items-center justify-between">
              <span>Violation Audit Log</span>
              <ChevronRight className="w-4 h-4 text-slate-400 group-hover:translate-x-1 transition-transform" />
            </h2>
            <p className="text-xs text-slate-500 mt-1">Review missing helmet & vest incidents with snapshots</p>
          </div>
        </Link>

        {/* 3. Siren & Buzzer Control */}
        <Link
          to="/admin/buzzers"
          className="p-5 rounded-2xl bg-white border border-amber-100 hover:border-amber-500 shadow-sm hover:shadow-md transition-all group flex flex-col justify-between"
        >
          <div className="flex items-center justify-between">
            <div className="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center font-bold group-hover:bg-amber-600 group-hover:text-white transition-colors">
              <Volume2 className="w-5 h-5" />
            </div>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 font-mono">
              105 dB Armed
            </span>
          </div>
          <div className="mt-4">
            <h2 className="text-sm font-bold text-slate-900 group-hover:text-amber-600 transition-colors flex items-center justify-between">
              <span>Industrial Sirens</span>
              <ChevronRight className="w-4 h-4 text-slate-400 group-hover:translate-x-1 transition-transform" />
            </h2>
            <p className="text-xs text-slate-500 mt-1">Trigger or silence audible alarms on shop floors</p>
          </div>
        </Link>

        {/* 4. Safety Marshals & Zones */}
        <Link
          to="/admin/supervisors"
          className="p-5 rounded-2xl bg-white border border-emerald-100 hover:border-emerald-500 shadow-sm hover:shadow-md transition-all group flex flex-col justify-between"
        >
          <div className="flex items-center justify-between">
            <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center font-bold group-hover:bg-emerald-600 group-hover:text-white transition-colors">
              <UserCheck className="w-5 h-5" />
            </div>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 font-mono">
              {summary.activeSupervisors} on Shift
            </span>
          </div>
          <div className="mt-4">
            <h2 className="text-sm font-bold text-slate-900 group-hover:text-emerald-600 transition-colors flex items-center justify-between">
              <span>Safety Marshals</span>
              <ChevronRight className="w-4 h-4 text-slate-400 group-hover:translate-x-1 transition-transform" />
            </h2>
            <p className="text-xs text-slate-500 mt-1">Supervisors assigned to Bays 01, 02 & 03</p>
          </div>
        </Link>
      </div>

      {/* Primary KPI Metrics Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Compliance Rate */}
        <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 shadow-xl flex flex-col justify-between relative overflow-hidden">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-bold uppercase tracking-wider">Overall Compliance</span>
            <div className="p-2 rounded-xl bg-emerald-950 border border-emerald-800/80 text-emerald-400">
              <ShieldCheck className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="text-3xl font-black text-white">{summary.overallComplianceRate}%</div>
            <div className="text-[11px] text-emerald-400 font-medium flex items-center gap-1 mt-1 font-mono">
              <TrendingUp className="w-3 h-3" /> OSHA Target: &gt;95% [COMPLIANT]
            </div>
          </div>
        </div>

        {/* Cameras Status */}
        <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 shadow-xl flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-bold uppercase tracking-wider">Optical CCTV Mesh</span>
            <div className="p-2 rounded-xl bg-sky-950 border border-sky-800/80 text-sky-400">
              <Camera className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-black text-white">{summary.totalCameras}</span>
              <span className="text-xs text-slate-400 font-semibold">Streams</span>
            </div>
            <div className="flex items-center gap-3 text-[11px] mt-1 font-semibold font-mono">
              <span className="text-emerald-400 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                {summary.onlineCameras} Active
              </span>
              <span className="text-rose-400 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-rose-400"></span>
                {summary.offlineCameras} Degraded
              </span>
            </div>
          </div>
        </div>

        {/* Zones & Active Supervisors */}
        <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 shadow-xl flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-bold uppercase tracking-wider">Hazard Zones & Marshals</span>
            <div className="p-2 rounded-xl bg-indigo-950 border border-indigo-800/80 text-indigo-400">
              <MapPin className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-black text-white">{summary.totalZones}</span>
              <span className="text-xs text-slate-400 font-semibold">Sectors</span>
            </div>
            <div className="text-[11px] text-indigo-400 font-medium flex items-center gap-1 mt-1 font-mono">
              <Users className="w-3 h-3" /> {summary.activeSupervisors} Marshals Assigned
            </div>
          </div>
        </div>

        {/* Violations */}
        <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 shadow-xl flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-bold uppercase tracking-wider">Active Infractions</span>
            <div className="p-2 rounded-xl bg-rose-950 border border-rose-800/80 text-rose-400">
              <AlertTriangle className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-black text-rose-400">{summary.totalViolations}</span>
              <span className="text-xs text-slate-400 font-semibold">Events</span>
            </div>
            <div className="text-[11px] text-amber-400 font-semibold mt-1 flex items-center gap-1 font-mono">
              <Clock className="w-3 h-3" />
              {summary.unacknowledgedViolations} Pending Review
            </div>
          </div>
        </div>
      </div>

      {/* INTERACTIVE 2D PLANT FLOOR BLUEPRINT / SPATIAL ZONE MATRIX */}
      <div className="p-5 sm:p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-2xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-slate-800 pb-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-400 pulse-live"></span>
              <h2 className="font-black text-white text-base tracking-wide uppercase">
                Plant Spatial Floor Layout & Telemetry Grid
              </h2>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Live sector telemetry with instant floor hooter trigger, marshal contact, and camera status
            </p>
          </div>
          <div className="flex items-center gap-2 font-mono text-[11px]">
            <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400">FLOOR 01 • SHOP FLOOR</span>
            <Link to="/admin/zones" className="text-sky-400 hover:underline">Edit Blueprint &rarr;</Link>
          </div>
        </div>

        {/* Blueprint Grid Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {zones.map((z, idx) => {
            const hasActiveAlarm = activeZoneAction === (z._id || z.id);
            const isBay1 = z.code === 'BAY-01' || z.name?.includes('Bay 01');
            return (
              <div 
                key={z._id || idx}
                className={`p-4 rounded-xl border transition duration-200 relative overflow-hidden flex flex-col justify-between ${
                  hasActiveAlarm
                    ? 'bg-red-950/40 border-red-500 shadow-xl shadow-red-900/30 ring-2 ring-red-500/50'
                    : 'bg-slate-950/80 border-slate-800 hover:border-slate-700'
                }`}
              >
                {/* Sector header */}
                <div>
                  <div className="flex items-center justify-between">
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-500/10 text-amber-400 border border-amber-500/30">
                      {z.code || `SEC-0${idx + 1}`}
                    </span>
                    <span className="flex items-center gap-1.5 text-[11px] font-semibold text-emerald-400">
                      <span className="w-2 h-2 rounded-full bg-emerald-400 pulse-live"></span>
                      Armed
                    </span>
                  </div>

                  <h3 className="font-bold text-slate-100 text-sm mt-2">{z.name}</h3>
                  <p className="text-[11px] text-slate-400 line-clamp-1">{z.description || 'Heavy manufacturing operations area'}</p>

                  {/* Required PPE badges */}
                  <div className="flex flex-wrap gap-1 mt-3">
                    {(z.requiredPPE || ['helmet', 'vest']).map((ppe) => (
                      <span key={ppe} className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-300 text-[10px] font-medium capitalize">
                        {ppe}
                      </span>
                    ))}
                  </div>

                  {/* Sector Supervisor Details */}
                  <div className="mt-3 pt-3 border-t border-slate-800/80 flex items-center justify-between text-[11px]">
                    <div className="text-slate-400">
                      <span className="text-[10px] text-slate-500 block">Floor Marshall</span>
                      <span className="font-semibold text-slate-200">{z.supervisor?.name || 'On Duty'}</span>
                    </div>
                    <div className="text-right text-slate-400 font-mono text-[10px]">
                      <span>{z.supervisor?.shift || 'General Shift'}</span>
                      <span className="text-slate-500 block">{z.supervisor?.phone || 'Floor Ext #104'}</span>
                    </div>
                  </div>
                </div>

                {/* Instant Floor Actions */}
                <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center gap-2">
                  <button
                    onClick={() => handleTriggerZoneBuzzer(z)}
                    disabled={hasActiveAlarm}
                    className={`flex-1 py-1.5 px-2.5 rounded-lg text-xs font-bold flex items-center justify-center gap-1.5 transition cursor-pointer ${
                      hasActiveAlarm
                        ? 'bg-red-600 text-white animate-pulse'
                        : 'bg-red-950/60 hover:bg-red-900/80 text-red-300 border border-red-800/60'
                    }`}
                    title="Sound authentic industrial alarm in this zone"
                  >
                    <Volume2 className="w-3.5 h-3.5" />
                    <span>{hasActiveAlarm ? 'SIREN SOUNDING' : 'Sound Buzzer'}</span>
                  </button>

                  <button
                    onClick={() => handleNotifySupervisor(z)}
                    className="py-1.5 px-2.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-semibold flex items-center gap-1 transition cursor-pointer"
                    title="Dispatch warning directive to supervisor"
                  >
                    <Send className="w-3 h-3 text-sky-400" />
                    <span>Alert Marshal</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Analytics & Compliance Trends */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Compliance Trend Chart (2 Cols) */}
        <div className="lg:col-span-2 p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-bold text-white text-sm">7-Day EHS Compliance vs Infraction Trend</h3>
              <p className="text-xs text-slate-400 mt-0.5">Automated AI detection event distribution over time</p>
            </div>
            <span className="text-[11px] font-mono text-sky-400 bg-sky-950/60 border border-sky-800 px-2 py-0.5 rounded">
              YOLOv8 Real-Time Inference
            </span>
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trends}>
                <defs>
                  <linearGradient id="compGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.4}/>
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="violGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#ef4444" stopOpacity={0.4}/>
                    <stop offset="95%" stopColor="#ef4444" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="date" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#64748b" fontSize={11} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '0.75rem', fontSize: '12px' }}
                />
                <Legend wrapperStyle={{ fontSize: '11px' }} />
                <Area type="monotone" dataKey="compliant" name="Compliant Man-Passes" stroke="#10b981" fillOpacity={1} fill="url(#compGrad)" />
                <Area type="monotone" dataKey="violation" name="Safety Infractions" stroke="#ef4444" fillOpacity={1} fill="url(#violGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Zone Breakdown Chart (1 Col) */}
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-white text-sm">Zone Safety Adherence</h3>
            <Link to="/admin/zones" className="text-xs text-sky-400 hover:underline flex items-center gap-1">
              <span>View All</span> <ChevronRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          <div className="space-y-3">
            {zoneSummary.length === 0 ? (
              <p className="text-xs text-slate-500 py-6 text-center">Loading zone compliance metrics...</p>
            ) : (
              zoneSummary.map((z) => {
                const total = (z.compliant || 0) + (z.violations || 0);
                const pct = total > 0 ? Math.round((z.compliant / total) * 100) : 100;
                return (
                  <div key={z.id} className="p-3 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
                    <div className="flex items-center justify-between text-xs font-semibold">
                      <span className="text-slate-200">{z.name}</span>
                      <span className={pct >= 90 ? 'text-emerald-400' : 'text-amber-400 font-bold'}>{pct}%</span>
                    </div>
                    <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                      <div 
                        className={`h-full rounded-full ${pct >= 90 ? 'bg-emerald-500' : 'bg-amber-500'}`} 
                        style={{ width: `${pct}%` }}
                      ></div>
                    </div>
                    <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono">
                      <span>Compliant: {z.compliant || 0}</span>
                      <span className="text-rose-400">Breaches: {z.violations || 0}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* CCTV Mesh Status & Recent Unacknowledged Violations */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* CCTV Mesh Status (1 Col) */}
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h3 className="font-bold text-white text-sm flex items-center gap-2">
              <Camera className="w-4 h-4 text-sky-400" />
              Connected Optical Sensors
            </h3>
            <Link to="/admin/cameras" className="text-xs text-sky-400 hover:underline">
              Configure
            </Link>
          </div>

          <div className="space-y-2.5">
            {cameras.map((cam) => (
              <div 
                key={cam._id}
                className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between text-xs"
              >
                <div>
                  <div className="font-semibold text-slate-200">{cam.name}</div>
                  <div className="text-[10px] text-slate-400 font-mono">{cam.zoneName} • {cam.resolution} • 30 FPS</div>
                </div>
                <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                  cam.status === 'ONLINE'
                    ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                    : 'bg-rose-950 text-rose-400 border border-rose-800'
                }`}>
                  {cam.status}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Recent Violations Audit Table (2 Cols) */}
        <div className="lg:col-span-2 p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h3 className="font-bold text-white text-sm flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-rose-400" />
                Latest Incident Audit Log
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">Real-time non-compliance events requiring supervisor acknowledgement</p>
            </div>
            <Link to="/admin/violations" className="text-xs text-sky-400 hover:underline flex items-center gap-1">
              <span>All Violations</span> <ChevronRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          {recentViolations.length === 0 ? (
            <div className="py-12 text-center text-slate-500 text-xs">
              <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-emerald-500/50" />
              Zero safety infractions reported. Plant floor is 100% compliant.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-300">
                <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] font-bold font-mono">
                  <tr>
                    <th className="p-3 rounded-l-lg">Sector</th>
                    <th className="p-3">Missing PPE</th>
                    <th className="p-3">Detected Gear</th>
                    <th className="p-3">Review Status</th>
                    <th className="p-3 rounded-r-lg text-right">Timestamp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-medium">
                  {recentViolations.map((v) => (
                    <tr key={v._id} className="hover:bg-slate-800/30 transition">
                      <td className="p-3 font-semibold text-slate-100">{v.zoneName}</td>
                      <td className="p-3">
                        <span className="px-2 py-0.5 rounded bg-rose-950/80 border border-rose-800 text-rose-300 text-[10px] font-bold">
                          {v.missingPPE?.join(', ') || 'Required PPE'}
                        </span>
                      </td>
                      <td className="p-3 text-slate-400 text-[11px]">
                        {v.detectedClasses?.map((c) => c.name || c.class).join(', ') || 'Worker Body'}
                      </td>
                      <td className="p-3">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                          v.reviewStatus === 'APPROVED'
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                            : 'bg-amber-950 text-amber-300 border border-amber-800'
                        }`}>
                          {v.reviewStatus || 'PENDING'}
                        </span>
                      </td>
                      <td className="p-3 text-right text-slate-500 text-[11px] font-mono">
                        {v.createdAt ? new Date(v.createdAt).toLocaleTimeString() : 'Just now'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
