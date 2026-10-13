import React, { useState, useEffect } from 'react';
import { 
  Bell, 
  Search, 
  RefreshCw, 
  AlertTriangle, 
  CheckCircle2, 
  MapPin, 
  Phone, 
  Clock, 
  Send,
  Filter
} from 'lucide-react';
import api from '../services/api';

export default function AdminNotificationsPage() {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedZone, setSelectedZone] = useState('ALL');
  const [zones, setZones] = useState([]);

  const fetchNotifications = async () => {
    setLoading(true);
    try {
      const [notifRes, zoneRes] = await Promise.allSettled([
        api.get('/notifications'),
        api.get('/zones'),
      ]);
      if (notifRes.status === 'fulfilled') setNotifications(notifRes.value.data || []);
      if (zoneRes.status === 'fulfilled') setZones(zoneRes.value.data || []);
    } catch (err) {
      console.error('Fetch notifications error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNotifications();
  }, []);

  const filtered = notifications.filter((n) => {
    const matchesSearch = 
      (n.zoneName || '').toLowerCase().includes(search.toLowerCase()) ||
      (n.supervisorName || '').toLowerCase().includes(search.toLowerCase()) ||
      (n.message || '').toLowerCase().includes(search.toLowerCase());

    const matchesZone = selectedZone === 'ALL' || n.zoneId === selectedZone || n.zoneName === selectedZone;
    return matchesSearch && matchesZone;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl lg:text-2xl font-bold text-white tracking-tight">Supervisor Notifications Ledger</h1>
            <span className="px-2 py-0.5 rounded-full bg-sky-950 border border-sky-800 text-sky-400 text-[10px] font-bold">
              {notifications.length} Alerts Dispatched
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Real-time audit log of automated SMS, WhatsApp, and email alerts delivered to zone supervisors upon PPE violations
          </p>
        </div>

        <button
          onClick={fetchNotifications}
          disabled={loading}
          className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-200 text-xs font-semibold border border-slate-700 transition self-start sm:self-auto"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh Ledger</span>
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="relative w-full sm:w-72">
          <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by zone, supervisor, or text..."
            className="w-full bg-slate-950 border border-slate-700 rounded-xl pl-9 pr-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <Filter className="w-4 h-4 text-slate-400" />
          <select
            value={selectedZone}
            onChange={(e) => setSelectedZone(e.target.value)}
            className="bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
          >
            <option value="ALL">All Facility Zones</option>
            {zones.map((z) => (
              <option key={z._id} value={z._id}>
                {z.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Notifications Table */}
      <div className="rounded-2xl bg-slate-900 border border-slate-800 shadow-xl overflow-hidden">
        {loading ? (
          <div className="py-16 text-center text-slate-400 text-xs">
            <div className="w-6 h-6 border-2 border-sky-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
            Loading notifications audit ledger...
          </div>
        ) : filtered.length === 0 ? (
          <div className="py-16 text-center text-slate-500 text-xs">
            <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-emerald-500/40" />
            No supervisor notifications match the selected filter.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] font-bold border-b border-slate-800">
                <tr>
                  <th className="p-3.5">Zone & Sector</th>
                  <th className="p-3.5">Assigned Supervisor</th>
                  <th className="p-3.5">Missing PPE Item</th>
                  <th className="p-3.5">Dispatch Channel</th>
                  <th className="p-3.5">Status</th>
                  <th className="p-3.5 text-right">Dispatched Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-medium">
                {filtered.map((n) => (
                  <tr key={n._id} className="hover:bg-slate-800/30 transition">
                    <td className="p-3.5">
                      <div className="font-bold text-slate-100">{n.zoneName}</div>
                      <div className="text-[10px] text-slate-500 font-mono">ID: {n.zoneId}</div>
                    </td>
                    <td className="p-3.5">
                      <div className="font-semibold text-slate-200">{n.supervisorName}</div>
                      <div className="text-[10px] text-slate-400 flex items-center gap-1 mt-0.5">
                        <Phone className="w-2.5 h-2.5 text-emerald-400" />
                        <span>{n.supervisorPhone || 'N/A'}</span>
                      </div>
                    </td>
                    <td className="p-3.5">
                      <span className="px-2 py-0.5 rounded bg-rose-950/80 border border-rose-800 text-rose-300 text-[10px] font-bold">
                        {n.missingPPE?.join(', ') || 'Safety Violations'}
                      </span>
                    </td>
                    <td className="p-3.5 text-slate-300">
                      <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-[10px] font-semibold border border-slate-700">
                        {n.alertChannel || 'SMS & WhatsApp'}
                      </span>
                    </td>
                    <td className="p-3.5">
                      <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] font-bold">
                        {n.deliveryStatus || 'DELIVERED'}
                      </span>
                    </td>
                    <td className="p-3.5 text-right font-mono text-[11px] text-slate-400">
                      {n.timestamp ? new Date(n.timestamp).toLocaleString() : 'Just now'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
