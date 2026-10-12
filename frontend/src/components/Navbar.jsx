import React, { useState, useEffect } from 'react';
import { Menu, Bell, Shield, Activity, Wifi, WifiOff, HardHat, CheckCircle2, AlertTriangle } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { getSocket } from '../services/socket';
import api, { AI_BASE_URL } from '../services/api';

export default function Navbar({ toggleSidebar }) {
  const { user } = useAuth();
  const [notifications, setNotifications] = useState([]);
  const [showNotifications, setShowNotifications] = useState(false);
  const [backendHealthy, setBackendHealthy] = useState(true);
  const [aiHealthy, setAiHealthy] = useState(false);

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

  // Real-time violation alerts via socket
  useEffect(() => {
    const socket = getSocket();
    if (!socket) return;

    const handleNewViolation = (event) => {
      setNotifications((prev) => [
        {
          id: event._id || Date.now(),
          zone: event.zoneName || 'Monitored Area',
          missingPPE: event.missingPPE || [],
          timestamp: new Date().toLocaleTimeString(),
          unread: true,
        },
        ...prev.slice(0, 9),
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

  return (
    <header className="h-16 bg-slate-900/80 backdrop-blur-md border-b border-slate-800 sticky top-0 z-30 px-4 lg:px-8 flex items-center justify-between">
      <div className="flex items-center gap-4">
        <button
          onClick={toggleSidebar}
          className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 lg:hidden"
        >
          <Menu className="w-5 h-5" />
        </button>
        <div className="flex items-center gap-2">
          <span className="hidden sm:inline-block font-semibold text-slate-200 text-sm tracking-wide">
            Enterprise Industrial Safety Suite
          </span>
          <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-slate-800 text-sky-400 border border-slate-700">
            v2.4 LTS
          </span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        {/* Service status indicators */}
        <div className="hidden md:flex items-center gap-3 px-3 py-1.5 rounded-full bg-slate-950/60 border border-slate-800 text-xs">
          <div className="flex items-center gap-1.5" title="Node.js API Server">
            <span className={`w-2 h-2 rounded-full ${backendHealthy ? 'bg-emerald-400 pulse-live' : 'bg-red-400'}`}></span>
            <span className="text-slate-400 text-[11px]">Backend API</span>
          </div>
          <span className="text-slate-700">|</span>
          <div className="flex items-center gap-1.5" title="Python YOLO Inference Service">
            <span className={`w-2 h-2 rounded-full ${aiHealthy ? 'bg-emerald-400 pulse-live' : 'bg-amber-400'}`}></span>
            <span className="text-slate-400 text-[11px]">AI Vision {aiHealthy ? '(Ready)' : '(Standby)'}</span>
          </div>
        </div>

        {/* Real-time notifications bell */}
        <div className="relative">
          <button
            onClick={() => setShowNotifications(!showNotifications)}
            className="relative p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
            title="Real-time Violation Alerts"
          >
            <Bell className="w-5 h-5" />
            {unreadCount > 0 && (
              <span className="absolute top-1 right-1 w-4 h-4 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center animate-pulse">
                {unreadCount}
              </span>
            )}
          </button>

          {/* Notifications Dropdown */}
          {showNotifications && (
            <div className="absolute right-0 mt-2 w-80 bg-slate-900 border border-slate-800 rounded-xl shadow-2xl p-3 z-50 animate-in fade-in zoom-in-95">
              <div className="flex items-center justify-between pb-2 border-b border-slate-800 mb-2">
                <span className="text-xs font-bold text-slate-200">Violation Alerts</span>
                {notifications.length > 0 && (
                  <button
                    onClick={markAllRead}
                    className="text-[10px] text-sky-400 hover:underline"
                  >
                    Mark all read
                  </button>
                )}
              </div>

              {notifications.length === 0 ? (
                <div className="py-6 text-center text-xs text-slate-500">
                  <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-emerald-500/60" />
                  No active violation alerts
                </div>
              ) : (
                <div className="space-y-2 max-h-72 overflow-y-auto">
                  {notifications.map((n) => (
                    <div
                      key={n.id}
                      className={`p-2.5 rounded-lg border text-xs flex gap-2.5 ${
                        n.unread
                          ? 'bg-red-950/30 border-red-800/50 text-slate-200'
                          : 'bg-slate-800/40 border-slate-800 text-slate-400'
                      }`}
                    >
                      <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                      <div>
                        <div className="font-semibold text-red-300">{n.zone}</div>
                        <div className="text-[11px] text-slate-400">
                          Missing: {n.missingPPE.join(', ') || 'Required Gear'}
                        </div>
                        <div className="text-[10px] text-slate-500 mt-1">{n.timestamp}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* User badge */}
        <div className="flex items-center gap-2 pl-2 border-l border-slate-800">
          <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center font-bold text-white text-xs shadow-md">
            {user?.name ? user.name[0].toUpperCase() : 'U'}
          </div>
          <span className="hidden sm:inline-block text-xs font-medium text-slate-300">
            {user?.name || 'Inspector'}
          </span>
        </div>
      </div>
    </header>
  );
}
