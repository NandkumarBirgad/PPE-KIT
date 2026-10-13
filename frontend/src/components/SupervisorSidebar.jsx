import React from 'react';
import { NavLink } from 'react-router-dom';
import { 
  LayoutDashboard, 
  Camera, 
  AlertTriangle, 
  Bell, 
  Volume2, 
  LogOut, 
  HardHat,
  UserCheck,
  MapPin,
  ShieldCheck
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const supervisorNavItems = [
  { name: 'My Zone Dashboard', path: '/supervisor/dashboard', icon: LayoutDashboard },
  { name: 'Live Zone Cameras', path: '/supervisor/live', icon: Camera },
  { name: 'Zone Violations', path: '/supervisor/violations', icon: AlertTriangle },
  { name: 'Floor Buzzer Control', path: '/supervisor/buzzers', icon: Volume2 },
  { name: 'Dispatched Alerts', path: '/supervisor/notifications', icon: Bell },
];

export default function SupervisorSidebar({ isOpen, setIsOpen }) {
  const { user, logout } = useAuth();

  return (
    <aside className={`fixed inset-y-0 left-0 z-40 w-64 bg-slate-900 border-r border-slate-800 transition-transform duration-200 lg:translate-x-0 ${isOpen ? 'translate-x-0' : '-translate-x-full'} flex flex-col justify-between shadow-2xl`}>
      <div className="overflow-y-auto">
        {/* Brand Header */}
        <div className="h-16 flex items-center px-6 gap-3 border-b border-slate-800 bg-slate-950/60 sticky top-0 z-10 backdrop-blur-md">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-600 flex items-center justify-center text-slate-950 shadow-lg shadow-emerald-500/20 ring-2 ring-emerald-500/20">
            <HardHat className="w-6 h-6" />
          </div>
          <div>
            <span className="font-bold text-white tracking-wide text-base block leading-tight">PPE Vision</span>
            <span className="text-[10px] text-emerald-400 font-bold uppercase tracking-wider flex items-center gap-1">
              <UserCheck className="w-3 h-3 text-emerald-400" /> Zone Supervisor
            </span>
          </div>
        </div>

        {/* Assigned Zone Highlight Badge */}
        <div className="m-3 p-3 rounded-xl bg-emerald-950/40 border border-emerald-800/60">
          <span className="text-[9px] font-bold text-emerald-400 uppercase tracking-wider block mb-1 flex items-center gap-1">
            <MapPin className="w-3 h-3" /> Assigned Safety Sector
          </span>
          <div className="text-xs font-bold text-slate-100 truncate">
            {user?.assignedZoneName || 'Heavy Assembly Bay 01'}
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5 font-mono">
            ID: {user?.assignedZoneId || 'BAY-01'}
          </div>
        </div>

        {/* Navigation links */}
        <nav className="p-3 space-y-1">
          <div className="px-3 pt-2 pb-1 text-[10px] font-bold text-slate-500 uppercase tracking-wider">
            Sector Operations
          </div>
          {supervisorNavItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={() => setIsOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-semibold transition-all ${
                    isActive
                      ? 'bg-emerald-600 text-white shadow-md shadow-emerald-600/30'
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
      <div className="p-4 border-t border-slate-800 bg-slate-950/60">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-600 flex items-center justify-center font-bold text-white text-xs shadow-md">
              {user?.name ? user.name[0].toUpperCase() : 'S'}
            </div>
            <div className="truncate">
              <p className="text-xs font-semibold text-slate-200 truncate">{user?.name || 'Zone Supervisor'}</p>
              <p className="text-[10px] text-emerald-400 uppercase font-bold tracking-wider">ZONE_SUPERVISOR</p>
            </div>
          </div>
          <button
            onClick={logout}
            title="Log Out"
            className="p-2 rounded-lg text-slate-400 hover:text-red-400 hover:bg-slate-800 transition"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>

        <div className="flex items-center justify-between text-[11px] text-slate-500 pt-2 border-t border-slate-800/60">
          <span>Active Shift</span>
          <span className="flex items-center gap-1.5 text-emerald-400 font-semibold text-[10px]">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 pulse-live"></span>
            On Duty
          </span>
        </div>
      </div>
    </aside>
  );
}
