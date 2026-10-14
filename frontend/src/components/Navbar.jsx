import React, { useState, useEffect } from 'react';
import { 
  Menu, 
  Bell, 
  Shield, 
  Activity, 
  Wifi, 
  WifiOff, 
  HardHat, 
  CheckCircle2, 
  AlertTriangle, 
  Volume2, 
  VolumeX, 
  Clock, 
  Radio, 
  Building2, 
  Flame, 
  Siren,
  Power,
  Sun,
  Moon
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { getSocket } from '../services/socket';
import api, { AI_BASE_URL } from '../services/api';
import { playIndustrialSiren, playWarningHorn, stopAllSounds, isSirenActive } from '../services/soundAlerts';

export default function Navbar({ toggleSidebar }) {
  const { user } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [notifications, setNotifications] = useState([]);
  const [showNotifications, setShowNotifications] = useState(false);
  const [backendHealthy, setBackendHealthy] = useState(true);
  const [aiHealthy, setAiHealthy] = useState(false);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [sirenPlaying, setSirenPlaying] = useState(false);
  const [sirenModalOpen, setSirenModalOpen] = useState(false);
  const [emergencySilenced, setEmergencySilenced] = useState(false);

  // Live industrial 24-hour clock
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Compute shift based on current hour
  const getShiftInfo = () => {
    const hour = currentTime.getHours();
    if (hour >= 6 && hour < 14) {
      return { shift: 'SHIFT A', timeWindow: '06:00 - 14:00', lead: 'Morning Heavy Ops' };
    } else if (hour >= 14 && hour < 22) {
      return { shift: 'SHIFT B', timeWindow: '14:00 - 22:00', lead: 'Afternoon Assembly' };
    } else {
      return { shift: 'SHIFT C', timeWindow: '22:00 - 06:00', lead: 'Night Shift / Maintenance' };
    }
  };

  const shiftInfo = getShiftInfo();

  // Health checks
  useEffect(() => {
    const checkServices = async () => {
      try {
        const res = await api.get('/health');
        setBackendHealthy(res.status === 200);
      } catch (e) {
        setBackendHealthy(false);
      }

      try {
        const res = await fetch(`${AI_BASE_URL}/health`);
        setAiHealthy(res.ok);
      } catch (e) {
        setAiHealthy(false);
      }
    };

    checkServices();
    const interval = setInterval(checkServices, 15000);
    return () => clearInterval(interval);
  }, []);

  // Fetch real supervisor notifications from API
  useEffect(() => {
    const fetchApiNotifications = async () => {
      try {
        const res = await api.get('/notifications');
        if (res.data && Array.isArray(res.data)) {
          setNotifications(res.data.map((n) => ({
            id: n._id,
            zone: n.zoneName || 'Safety Zone',
            supervisor: n.supervisorName || 'Floor Supervisor',
            channel: n.alertChannel || 'SMS/WhatsApp',
            missingPPE: n.missingPPE || [],
            timestamp: n.timestamp ? new Date(n.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString(),
            unread: true,
          })));
        }
      } catch (err) {
        // quiet fallback
      }
    };

    fetchApiNotifications();
    const notifInterval = setInterval(fetchApiNotifications, 10000);
    return () => clearInterval(notifInterval);
  }, []);

  // Real-time violation alerts via socket
  useEffect(() => {
    const socket = getSocket();
    if (!socket) return;

    const handleNewViolation = (event) => {
      setNotifications((prev) => [
        {
          id: event._id || Date.now(),
          zone: event.zoneName || 'Monitored Area',
          supervisor: event.supervisorName || 'Zone Supervisor',
          channel: event.alertChannel || 'SMS',
          missingPPE: event.missingPPE || [],
          timestamp: new Date().toLocaleTimeString(),
          unread: true,
        },
        ...prev.slice(0, 19),
      ]);
    };

    socket.on('violation:new', handleNewViolation);
    return () => {
      socket.off('violation:new', handleNewViolation);
    };
  }, []);

  const unreadCount = notifications.filter((n) => n.unread).length;

  const markAllRead = () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, unread: false })));
  };

  const handleTriggerEmergencySiren = async () => {
    setSirenPlaying(true);
    setEmergencySilenced(false);
    playIndustrialSiren(5);
    try {
      await api.post('/buzzers/silence-all', { state: 'ARMED' }).catch(() => {});
    } catch (e) {}

    setTimeout(() => {
      setSirenPlaying(false);
    }, 5000);
  };

  const handleSilenceAll = async () => {
    stopAllSounds();
    setSirenPlaying(false);
    setEmergencySilenced(true);
    try {
      await api.post('/buzzers/silence-all', { state: 'MUTED' });
    } catch (e) {}
  };

  return (
    <header className="h-16 bg-slate-950/90 backdrop-blur-md border-b border-slate-800 sticky top-0 z-30 px-3 sm:px-6 flex items-center justify-between shadow-lg">
      {/* Left: Hamburger + Plant Identity & Telemetry */}
      <div className="flex items-center gap-3">
        <button
          onClick={toggleSidebar}
          className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 lg:hidden cursor-pointer"
          title="Toggle Navigation Menu"
        >
          <Menu className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-2.5">
          <div className="hidden sm:flex items-center gap-2 px-2.5 py-1 rounded-md bg-slate-900 border border-slate-800">
            <Building2 className="w-3.5 h-3.5 text-amber-400" />
            <div className="leading-tight">
              <span className="text-[11px] font-bold tracking-wider text-slate-200 uppercase">
                Plant Unit-04
              </span>
              <span className="text-[9px] text-slate-500 block font-mono">
                CHAKAN INDUSTRIAL ZONE
              </span>
            </div>
          </div>

          <div className="hidden md:flex items-center gap-2 px-2.5 py-1 rounded-md bg-slate-900/80 border border-slate-800 font-mono text-[11px]">
            <span className="w-2 h-2 rounded-full bg-emerald-400 pulse-live"></span>
            <span className="text-amber-400 font-bold">{shiftInfo.shift}</span>
            <span className="text-slate-500">({shiftInfo.timeWindow})</span>
          </div>
        </div>
      </div>

      {/* Center: Live Plant Clock & EHS Threat Level */}
      <div className="hidden lg:flex items-center gap-4">
        <div className="flex items-center gap-2 px-3 py-1 rounded-md bg-slate-900/90 border border-slate-800/80 font-mono text-xs text-slate-300">
          <Clock className="w-3.5 h-3.5 text-sky-400" />
          <span>{currentTime.toLocaleTimeString('en-US', { hour12: false })} IST</span>
          <span className="text-slate-600">|</span>
          <span className="text-[10px] text-slate-400">
            {currentTime.toISOString().slice(0, 10)}
          </span>
        </div>

        <div className={`flex items-center gap-2 px-2.5 py-1 rounded-md border text-xs font-semibold ${
          unreadCount > 0 
            ? 'bg-red-950/40 border-red-800/80 text-red-300 animate-pulse' 
            : 'bg-emerald-950/30 border-emerald-800/50 text-emerald-300'
        }`}>
          <Shield className="w-3.5 h-3.5" />
          <span className="text-[11px] uppercase tracking-wider">
            {unreadCount > 0 ? `EHS ADVISORY: ${unreadCount} ALERTS` : 'EHS THREAT: LEVEL 1 (NORMAL)'}
          </span>
        </div>
      </div>

      {/* Right: Master Siren Trigger, Silence, Notifications & User */}
      <div className="flex items-center gap-2 sm:gap-3">
        {/* Master Industrial Siren Test / Emergency Sounder Button */}
        <div className="flex items-center gap-1.5 bg-slate-900/90 p-1 rounded-lg border border-slate-800">
          <button
            onClick={handleTriggerEmergencySiren}
            disabled={sirenPlaying}
            className={`px-2.5 py-1 rounded text-[11px] font-bold flex items-center gap-1.5 transition cursor-pointer ${
              sirenPlaying
                ? 'bg-red-600 text-white animate-bounce'
                : 'bg-red-950/70 hover:bg-red-900/90 text-red-300 border border-red-800/60'
            }`}
            title="Sound Plant Alarm Siren (Test/Emergency)"
          >
            <Siren className={`w-3.5 h-3.5 ${sirenPlaying ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">
              {sirenPlaying ? 'SIREN ACTIVE' : 'TEST SIREN'}
            </span>
          </button>

          <button
            onClick={handleSilenceAll}
            className="p-1 rounded text-slate-400 hover:text-white hover:bg-slate-800 transition cursor-pointer"
            title="Silence All Floor Buzzers & Sirens"
          >
            <VolumeX className="w-4 h-4 text-amber-400" />
          </button>
        </div>

        {/* Vision AI & Backend telemetry status */}
        <div className="hidden xl:flex items-center gap-2 px-2.5 py-1 rounded-md bg-slate-900 border border-slate-800 text-[11px] font-mono">
          <div className="flex items-center gap-1">
            <span className={`w-1.5 h-1.5 rounded-full ${backendHealthy ? 'bg-emerald-400' : 'bg-red-400'}`}></span>
            <span className="text-slate-400">API</span>
          </div>
          <span className="text-slate-700">|</span>
          <div className="flex items-center gap-1">
            <span className={`w-1.5 h-1.5 rounded-full ${aiHealthy ? 'bg-emerald-400 pulse-live' : 'bg-amber-400'}`}></span>
            <span className="text-slate-400">YOLO</span>
          </div>
        </div>

        {/* White & Blue Theme Toggle Button */}
        <button
          onClick={toggleTheme}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-semibold transition cursor-pointer shadow-sm hover:scale-[1.02] active:scale-[0.98] bg-blue-50/90 hover:bg-blue-100 text-blue-700 border-blue-200"
          title={theme === 'white-blue' ? 'Switch to Dark Mode' : 'Switch to White & Blue UI'}
        >
          {theme === 'white-blue' ? (
            <>
              <Sun className="w-3.5 h-3.5 text-blue-600 animate-spin-slow" />
              <span className="hidden sm:inline font-mono text-[11px] font-bold">White / Blue</span>
            </>
          ) : (
            <>
              <Moon className="w-3.5 h-3.5 text-amber-400" />
              <span className="hidden sm:inline font-mono text-[11px]">Dark Mode</span>
            </>
          )}
        </button>

        {/* Notifications Bell */}
        <div className="relative">
          <button
            onClick={() => setShowNotifications(!showNotifications)}
            className="relative p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition cursor-pointer"
            title="Real-time Violation Alerts"
          >
            <Bell className="w-5 h-5" />
            {unreadCount > 0 && (
              <span className="absolute top-1 right-1 w-4 h-4 rounded-full bg-red-600 text-white text-[10px] font-bold flex items-center justify-center animate-pulse">
                {unreadCount}
              </span>
            )}
          </button>

          {/* Notifications Dropdown */}
          {showNotifications && (
            <div className="absolute right-0 mt-2 w-84 bg-slate-900 border border-slate-800 rounded-xl shadow-2xl p-3 z-50 animate-in fade-in zoom-in-95">
              <div className="flex items-center justify-between pb-2 border-b border-slate-800 mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-slate-200">Incident Dispatch Ledger</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 font-mono">
                    {notifications.length}
                  </span>
                </div>
                {notifications.length > 0 && (
                  <button
                    onClick={markAllRead}
                    className="text-[10px] text-sky-400 hover:underline cursor-pointer"
                  >
                    Acknowledge all
                  </button>
                )}
              </div>

              {notifications.length === 0 ? (
                <div className="py-6 text-center text-xs text-slate-500">
                  <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-emerald-500/60" />
                  No unresolved floor infractions
                </div>
              ) : (
                <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                  {notifications.map((n) => (
                    <div
                      key={n.id}
                      className={`p-2.5 rounded-lg border text-xs flex gap-2.5 ${
                        n.unread
                          ? 'bg-red-950/40 border-red-800/60 text-slate-200'
                          : 'bg-slate-800/40 border-slate-800 text-slate-400'
                      }`}
                    >
                      <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-red-300 truncate">{n.zone}</span>
                          <span className="text-[9px] text-slate-500 font-mono">{n.timestamp}</span>
                        </div>
                        <div className="text-[11px] text-slate-300 mt-0.5">
                          Missing: <span className="text-red-400 font-bold">{n.missingPPE.join(', ') || 'Mandatory PPE'}</span>
                        </div>
                        {n.supervisor && (
                          <div className="text-[10px] text-slate-400 mt-1 flex items-center justify-between">
                            <span>Marshal: <span className="text-amber-300">{n.supervisor}</span></span>
                            <span className="text-[9px] bg-slate-800 px-1.5 py-0.5 rounded text-slate-300 font-mono">
                              {n.channel}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* User identification badge */}
        <div className="flex items-center gap-2 pl-2 border-l border-slate-800">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-sky-600 to-indigo-600 flex items-center justify-center font-bold text-white text-xs shadow-md border border-sky-400/30">
            {user?.name ? user.name[0].toUpperCase() : 'U'}
          </div>
          <div className="hidden lg:block text-left leading-tight">
            <span className="text-xs font-semibold text-slate-200 block truncate max-w-[120px]">
              {user?.name || 'Safety Marshal'}
            </span>
            <span className="text-[9px] text-amber-400 font-mono block">
              {user?.role === 'SUPER_ADMIN' || user?.role === 'admin' ? 'EHS HEAD' : user?.assignedZoneName || 'ZONE LEAD'}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
