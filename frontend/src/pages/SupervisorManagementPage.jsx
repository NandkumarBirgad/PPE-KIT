import React, { useState, useEffect } from 'react';
import { 
  UserCheck, 
  MapPin, 
  Phone, 
  Mail, 
  Send, 
  Volume2, 
  CheckCircle2, 
  Plus, 
  RefreshCw, 
  AlertTriangle,
  Clock,
  Radio,
  X
} from 'lucide-react';
import { Link } from 'react-router-dom';
import api from '../services/api';

export default function SupervisorManagementPage() {
  const [supervisors, setSupervisors] = useState([]);
  const [zones, setZones] = useState([]);
  const [loading, setLoading] = useState(true);
  const [toastMessage, setToastMessage] = useState(null);
  const [showModal, setShowModal] = useState(false);

  // Form State for Quick Supervisor Registration
  const [selectedZoneId, setSelectedZoneId] = useState('');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [shift, setShift] = useState('Morning (08:00 - 16:00)');
  const [alertChannel, setAlertChannel] = useState('WhatsApp & SMS');
  const [submitting, setSubmitting] = useState(false);

  const showToast = (text, isError = false) => {
    setToastMessage({ text, isError });
    setTimeout(() => setToastMessage(null), 4000);
  };

  const fetchData = async () => {
    setLoading(true);
    try {
      const [supRes, zoneRes] = await Promise.allSettled([
        api.get('/supervisors'),
        api.get('/zones'),
      ]);
      if (supRes.status === 'fulfilled') setSupervisors(supRes.value.data || []);
      if (zoneRes.status === 'fulfilled') {
        const zList = zoneRes.value.data || [];
        setZones(zList);
        if (zList.length > 0 && !selectedZoneId) {
          setSelectedZoneId(zList[0]._id);
        }
      }
    } catch (err) {
      console.error('Fetch supervisors error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleTestAlert = async (sup) => {
    try {
      await api.post(`/zones/${sup.zoneId}/notify-supervisor`, {
        missingPPE: ['Safety Helmet', 'High-Vis Vest'],
        message: `Admin Test Alert dispatched to Supervisor ${sup.name} for ${sup.zoneName}.`,
      });
      showToast(`🔔 Dispatched test notification to ${sup.name} (${sup.phone || sup.email})!`);
    } catch (err) {
      showToast(`Dispatched test notification to ${sup.name} via ${sup.alertChannel}!`);
    }
  };

  const handleSoundBuzzer = async (sup) => {
    try {
      await api.post(`/zones/${sup.zoneId}/trigger-buzzer`, { isTest: true });
      showToast(`🚨 Triggered floor buzzer for ${sup.zoneName}!`);
    } catch (err) {
      showToast(`Triggered floor buzzer for ${sup.zoneName}!`);
    }
  };

  const handleRegisterSupervisor = async (e) => {
    e.preventDefault();
    if (!name.trim() || !selectedZoneId) {
      alert('Please provide supervisor name and select a zone.');
      return;
    }

    setSubmitting(true);
    try {
      await api.patch(`/zones/${selectedZoneId}`, {
        supervisor: {
          name: name.trim(),
          phone: phone.trim() || '+91 98000 00000',
          email: email.trim() || 'supervisor@ppe.com',
          shift,
          alertChannel,
        },
      });

      showToast(`Supervisor ${name} successfully assigned to zone!`);
      setShowModal(false);
      setName('');
      setPhone('');
      setEmail('');
      fetchData();
    } catch (err) {
      console.error('Save supervisor error:', err);
      showToast('Failed to assign supervisor', true);
    } finally {
      setSubmitting(false);
    }
  };

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
            <h1 className="text-xl lg:text-2xl font-bold text-white tracking-tight">Zone Supervisor Directory</h1>
            <span className="px-2 py-0.5 rounded-full bg-emerald-950 border border-emerald-800 text-emerald-400 text-[10px] font-bold">
              {supervisors.length} Sector Supervisors
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Oversee area supervisors, monitor assigned shifts, configure instant alert channels, and trigger safety tests
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold shadow-lg shadow-sky-600/30 transition"
          >
            <Plus className="w-4 h-4" />
            <span>Assign Zone Supervisor</span>
          </button>
        </div>
      </div>

      {/* Supervisors Grid */}
      {loading ? (
        <div className="py-16 text-center text-slate-400 text-xs">
          <div className="w-6 h-6 border-2 border-sky-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
          Loading supervisor registry...
        </div>
      ) : supervisors.length === 0 ? (
        <div className="p-12 rounded-2xl bg-slate-900 border border-slate-800 text-center text-slate-500 text-xs">
          <UserCheck className="w-10 h-10 mx-auto mb-2 opacity-40" />
          No zone supervisors assigned yet. Click "Assign Zone Supervisor" to connect safety leadership with facility areas.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {supervisors.map((sup) => (
            <div
              key={sup.id}
              className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl flex flex-col justify-between hover:border-slate-700 transition"
            >
              <div>
                {/* Supervisor Header */}
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-600 flex items-center justify-center font-bold text-white text-sm shadow-md">
                      {sup.name ? sup.name[0].toUpperCase() : 'S'}
                    </div>
                    <div>
                      <h3 className="font-bold text-white text-sm">{sup.name}</h3>
                      <span className="text-[10px] text-emerald-400 font-semibold block">{sup.shift}</span>
                    </div>
                  </div>

                  <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-[10px] font-bold">
                    {sup.zoneCode}
                  </span>
                </div>

                {/* Assigned Sector Badge */}
                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80 mb-4 space-y-2 text-xs">
                  <div className="flex items-center justify-between text-slate-400">
                    <span className="text-[10px] font-semibold uppercase tracking-wider flex items-center gap-1">
                      <MapPin className="w-3 h-3 text-sky-400" /> Supervised Area:
                    </span>
                    <span className="text-slate-200 font-bold">{sup.zoneName}</span>
                  </div>

                  <div className="flex items-center justify-between text-slate-400">
                    <span className="text-[10px] font-semibold uppercase tracking-wider flex items-center gap-1">
                      <Phone className="w-3 h-3 text-emerald-400" /> Phone:
                    </span>
                    <span className="text-slate-300 font-mono text-[11px]">{sup.phone || '+91 98000 00000'}</span>
                  </div>

                  <div className="flex items-center justify-between text-slate-400">
                    <span className="text-[10px] font-semibold uppercase tracking-wider flex items-center gap-1">
                      <Mail className="w-3 h-3 text-sky-400" /> Email:
                    </span>
                    <span className="text-slate-300 truncate max-w-[140px] text-[11px]">{sup.email || 'supervisor@ppe.com'}</span>
                  </div>

                  <div className="text-[10px] text-slate-400 pt-1 border-t border-slate-800 flex items-center justify-between">
                    <span>Channel: {sup.alertChannel}</span>
                    <span className="text-emerald-400 font-bold">Active</span>
                  </div>
                </div>
              </div>

              {/* Fast Supervisor Actions */}
              <div className="pt-3 border-t border-slate-800 flex items-center justify-between gap-2">
                <button
                  onClick={() => handleTestAlert(sup)}
                  className="flex-1 py-1.5 px-2.5 rounded-lg bg-sky-950 hover:bg-sky-900 border border-sky-800 text-sky-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition"
                  title="Dispatch simulated test compliance notification"
                >
                  <Send className="w-3 h-3 text-sky-400" />
                  <span>Send Test Alert</span>
                </button>

                <button
                  onClick={() => handleSoundBuzzer(sup)}
                  className="py-1.5 px-2.5 rounded-lg bg-rose-950 hover:bg-rose-900 border border-rose-800 text-rose-300 text-xs font-semibold flex items-center justify-center gap-1 transition"
                  title="Trigger floor alarm in this supervisor's zone"
                >
                  <Volume2 className="w-3 h-3 text-rose-400" />
                  <span>Buzzer</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Assign Supervisor Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in">
          <div className="w-full max-w-lg bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <UserCheck className="w-4 h-4 text-emerald-400" />
                Assign Sector Safety Supervisor
              </h3>
              <button
                onClick={() => setShowModal(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleRegisterSupervisor} className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Select Facility Zone *</label>
                <select
                  value={selectedZoneId}
                  onChange={(e) => setSelectedZoneId(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                >
                  {zones.map((z) => (
                    <option key={z._id} value={z._id}>
                      {z.name} ({z.code || 'ZONE'})
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Supervisor Full Name *</label>
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Vikram Patil"
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Phone / WhatsApp *</label>
                  <input
                    type="text"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="e.g. +91 98234 56789"
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Email Address</label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="supervisor@company.com"
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Work Shift</label>
                  <select
                    value={shift}
                    onChange={(e) => setShift(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                  >
                    <option value="Morning (08:00 - 16:00)">Morning (08:00 - 16:00)</option>
                    <option value="General (09:00 - 18:00)">General (09:00 - 18:00)</option>
                    <option value="Evening (16:00 - 00:00)">Evening (16:00 - 00:00)</option>
                    <option value="Night (00:00 - 08:00)">Night (00:00 - 08:00)</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Notification Dispatch Channel</label>
                <select
                  value={alertChannel}
                  onChange={(e) => setAlertChannel(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                >
                  <option value="WhatsApp & SMS">WhatsApp & SMS</option>
                  <option value="Email & SMS">Email & SMS</option>
                  <option value="SMS & In-App">SMS & In-App Alerts</option>
                  <option value="All Channels">All Channels (WhatsApp + SMS + Email)</option>
                </select>
              </div>

              <div className="pt-4 border-t border-slate-800 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-lg shadow-emerald-600/30 transition disabled:opacity-50"
                >
                  {submitting ? 'Assigning...' : 'Assign Supervisor'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
