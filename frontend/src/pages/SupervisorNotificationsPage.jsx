import React, { useState, useEffect } from 'react';
import { 
  Bell, 
  RefreshCw, 
  CheckCircle2, 
  MapPin, 
  Phone, 
  Send,
  AlertTriangle,
  Clock
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';

export default function SupervisorNotificationsPage() {
  const { user } = useAuth();
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [broadcastMessage, setBroadcastMessage] = useState('');
  const [broadcasting, setBroadcasting] = useState(false);
  const [toastMessage, setToastMessage] = useState('');

  const fetchNotifications = async () => {
    setLoading(true);
    try {
      const res = await api.get('/notifications');
      const all = res.data || [];
      // Filter for this supervisor's zone if assigned
      const filtered = user?.assignedZoneName
        ? all.filter((n) => n.zoneName === user.assignedZoneName || (n.zoneId && n.zoneId === user.assignedZoneId))
        : all;
      setNotifications(filtered.length > 0 ? filtered : all);
    } catch (err) {
      console.error('Fetch notifications error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNotifications();
  }, []);

  const handleBroadcast = async (e) => {
    e.preventDefault();
    if (!broadcastMessage.trim()) return;
    setBroadcasting(true);
    try {
      await api.post(`/zones/${user?.assignedZoneId || 'zone_01'}/notify-supervisor`, {
        missingPPE: ['Safety Notice Broadcast'],
        message: `📢 Supervisor Notice: ${broadcastMessage.trim()}`,
      });
      setToastMessage('Safety announcement dispatched to sector workers via SMS & WhatsApp!');
      setBroadcastMessage('');
      fetchNotifications();
      setTimeout(() => setToastMessage(''), 4500);
    } catch (err) {
      console.error('Broadcast error:', err);
    } finally {
      setBroadcasting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Toast Alert */}
      {toastMessage && (
        <div className="p-3.5 rounded-xl bg-emerald-950/80 border border-emerald-800 text-emerald-200 text-xs flex items-center justify-between shadow-xl">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>{toastMessage}</span>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl lg:text-2xl font-bold text-white tracking-tight">Supervisor Dispatched Alerts</h1>
            <span className="px-2 py-0.5 rounded-full bg-emerald-950 border border-emerald-800 text-emerald-400 text-[10px] font-bold">
              {user?.assignedZoneName || 'My Zone'}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Log of automated compliance alerts sent to your phone/WhatsApp when violations occur on the deck
          </p>
        </div>

        <button
          onClick={fetchNotifications}
          className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-200 text-xs font-semibold border border-slate-700 transition self-start sm:self-auto"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Quick Sector Broadcast Card */}
      <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-3">
        <h3 className="font-bold text-white text-xs uppercase tracking-wider flex items-center gap-2">
          <Send className="w-4 h-4 text-emerald-400" />
          Broadcast Instant Sector Safety Directive
        </h3>
        <form onSubmit={handleBroadcast} className="flex gap-2">
          <input
            type="text"
            value={broadcastMessage}
            onChange={(e) => setBroadcastMessage(e.target.value)}
            placeholder="e.g. Overhead crane movement in Bay 01. All staff verify hard hats now."
            className="flex-1 bg-slate-950 border border-slate-700 rounded-xl px-3.5 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
          />
          <button
            type="submit"
            disabled={broadcasting}
            className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold shadow-lg shadow-emerald-600/30 transition flex items-center gap-1.5 flex-shrink-0 disabled:opacity-50"
          >
            <Send className="w-3.5 h-3.5" />
            <span>Send Notice</span>
          </button>
        </form>
      </div>

      {/* Notifications Table */}
      <div className="rounded-2xl bg-slate-900 border border-slate-800 shadow-xl overflow-hidden">
        {loading ? (
          <div className="py-16 text-center text-slate-400 text-xs">
            <div className="w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
            Loading sector alert history...
          </div>
        ) : notifications.length === 0 ? (
          <div className="py-16 text-center text-slate-500 text-xs">
            <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-emerald-500/40" />
            No alerts dispatched for your sector yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] font-bold border-b border-slate-800">
                <tr>
                  <th className="p-3.5">Sector</th>
                  <th className="p-3.5">Violation / Directive Message</th>
                  <th className="p-3.5">Missing PPE</th>
                  <th className="p-3.5">Channel</th>
                  <th className="p-3.5 text-right">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-medium">
                {notifications.map((n) => (
                  <tr key={n._id} className="hover:bg-slate-800/30 transition">
                    <td className="p-3.5 font-bold text-slate-100">{n.zoneName}</td>
                    <td className="p-3.5 text-slate-300 max-w-sm">{n.message || 'Automated PPE violation alert'}</td>
                    <td className="p-3.5">
                      <span className="px-2 py-0.5 rounded bg-rose-950/80 border border-rose-800 text-rose-300 text-[10px] font-bold">
                        {n.missingPPE?.join(', ') || 'Safety Gear'}
                      </span>
                    </td>
                    <td className="p-3.5">
                      <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-[10px] font-semibold border border-slate-700">
                        {n.alertChannel || 'WhatsApp & SMS'}
                      </span>
                    </td>
                    <td className="p-3.5 text-right font-mono text-[11px] text-slate-400">
                      {n.timestamp ? new Date(n.timestamp).toLocaleTimeString() : 'Recent'}
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
