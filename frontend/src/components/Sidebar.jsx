import React from 'react';
import { NavLink } from 'react-router-dom';
import { 
  LayoutDashboard, 
  Camera, 
  UploadCloud, 
  AlertTriangle, 
  FileText, 
  MapPin, 
  Users, 
  Settings, 
  ShieldCheck, 
  HardHat,
  LogOut 
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const navItems = [
  { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
  { name: 'Live Monitoring', path: '/live', icon: Camera },
  { name: 'Upload & Detect', path: '/upload', icon: UploadCloud },
  { name: 'Violations History', path: '/violations', icon: AlertTriangle },
  { name: 'Reports & Analytics', path: '/reports', icon: FileText },
  { name: 'Zone Management', path: '/zones', icon: MapPin },
  { name: 'User Management', path: '/users', icon: Users, role: 'admin' },
  { name: 'System Settings', path: '/settings', icon: Settings },
];

export default function Sidebar({ isOpen, setIsOpen }) {
  const { user, logout } = useAuth();

  return (
    <aside className={`fixed inset-y-0 left-0 z-40 w-64 bg-slate-900 border-r border-slate-800 transition-transform duration-200 lg:translate-x-0 ${isOpen ? 'translate-x-0' : '-translate-x-full'} flex flex-col justify-between shadow-2xl`}>
      <div>
        {/* Header / Brand */}
        <div className="h-16 flex items-center px-6 gap-3 border-b border-slate-800 bg-slate-950/50">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-amber-500 to-amber-600 flex items-center justify-center text-slate-950 shadow-lg shadow-amber-500/20">
            <HardHat className="w-6 h-6" />
          </div>
          <div>
            <span className="font-bold text-white tracking-wide text-base block leading-tight">PPE Vision</span>
            <span className="text-[11px] text-amber-400 font-semibold uppercase tracking-wider">AI Compliance</span>
          </div>
        </div>

        {/* Navigation links */}
        <nav className="p-3 space-y-1">
          {navItems.map((item) => {
            if (item.role && user?.role !== item.role) return null;
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={() => setIsOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition-all ${
                    isActive
                      ? 'bg-sky-600 text-white shadow-md shadow-sky-600/30'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                  }`
                }
              >
                <Icon className="w-4 h-4 flex-shrink-0" />
                <span>{item.name}</span>
              </NavLink>
            );
          })}
        </nav>
      </div>

      {/* User profile & footer */}
      <div className="p-4 border-t border-slate-800 bg-slate-950/40">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="w-9 h-9 rounded-full bg-slate-700 flex items-center justify-center font-bold text-sky-400 text-sm">
              {user?.name ? user.name[0].toUpperCase() : 'U'}
            </div>
            <div className="truncate">
              <p className="text-xs font-semibold text-slate-200 truncate">{user?.name || 'Safety Inspector'}</p>
              <p className="text-[10px] text-sky-400 uppercase font-bold tracking-wider">{user?.role || 'Guest'}</p>
            </div>
          </div>
          <button
            onClick={logout}
            title="Log Out"
            className="p-1.5 rounded-lg text-slate-400 hover:text-red-400 hover:bg-slate-800 transition"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>

        <div className="flex items-center justify-between text-[11px] text-slate-500 pt-2 border-t border-slate-800/60">
          <span>AI Engine</span>
          <span className="flex items-center gap-1.5 text-emerald-400 font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 pulse-live"></span>
            YOLOv8 Active
          </span>
        </div>
      </div>
    </aside>
  );
}
