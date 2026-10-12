import React, { useState, useEffect } from 'react';
import { 
  MapPin, 
  Plus, 
  Edit3, 
  Trash2, 
  CheckCircle2, 
  X, 
  ShieldCheck, 
  AlertTriangle,
  Layers,
  Power,
  UserCheck,
  Phone,
  Mail,
  Camera,
  Volume2,
  VolumeX,
  Bell,
  Send,
  Radio,
  Clock,
  Sparkles
} from 'lucide-react';
import api from '../services/api';

const AVAILABLE_PPE = [
  { id: 'helmet', label: 'Safety Helmet / Hard Hat', icon: '⛑️' },
  { id: 'vest', label: 'High-Visibility Safety Vest', icon: '🦺' },
  { id: 'goggles', label: 'Protective Safety Goggles', icon: '🥽' },
  { id: 'gloves', label: 'Industrial Safety Gloves', icon: '🧤' },
  { id: 'mask', label: 'Respiratory / Face Mask', icon: '😷' },
  { id: 'boots', label: 'Steel-Toe Safety Boots', icon: '🥾' },
];

const ALERT_CHANNELS = [
  { id: 'WhatsApp & SMS', label: 'WhatsApp & SMS' },
  { id: 'Email & SMS', label: 'Email & SMS' },
  { id: 'SMS & In-App', label: 'SMS & In-App Alerts' },
  { id: 'All Channels', label: 'All Channels (WhatsApp + SMS + Email)' },
];

const BUZZER_SOUNDS = [
  { id: 'siren', label: '🚨 Industrial Emergency Siren' },
  { id: 'horn', label: '📢 High-Decibel Klaxon Horn' },
  { id: 'alarm', label: '⚡ Rapid Pulse Alarm' },
  { id: 'beep', label: '🔊 Standard Safety Beep' },
];

export default function ZoneManagementPage() {
  const [zones, setZones] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingZone, setEditingZone] = useState(null);
  const [toastMessage, setToastMessage] = useState(null);

  // Form State
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [description, setDescription] = useState('');
  const [requiredPPE, setRequiredPPE] = useState(['helmet', 'vest']);
  const [active, setActive] = useState(true);

  // Supervisor Form State
  const [supervisorName, setSupervisorName] = useState('');
  const [supervisorEmail, setSupervisorEmail] = useState('');
  const [supervisorPhone, setSupervisorPhone] = useState('');
  const [supervisorAlertChannel, setSupervisorAlertChannel] = useState('WhatsApp & SMS');
  const [supervisorShift, setSupervisorShift] = useState('Morning (08:00 - 16:00)');

  // Camera & Buzzer Form State
  const [cameraName, setCameraName] = useState('');
  const [cameraSourceType, setCameraSourceType] = useState('webcam');
  const [cameraStreamUrl, setCameraStreamUrl] = useState('');
  const [buzzerEnabled, setBuzzerEnabled] = useState(true);
  const [buzzerSound, setBuzzerSound] = useState('siren');

  const [formError, setFormError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState('general'); // 'general' | 'supervisor' | 'buzzer_camera'

  // Web Audio Context for Testing Buzzer Sound
  const playBuzzerAudio = (soundType = 'siren') => {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      const ctx = new AudioCtx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      if (soundType === 'horn') {
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(440, ctx.currentTime);
        osc.frequency.linearRampToValueAtTime(320, ctx.currentTime + 0.4);
      } else if (soundType === 'alarm') {
        osc.type = 'square';
        osc.frequency.setValueAtTime(950, ctx.currentTime);
        osc.frequency.linearRampToValueAtTime(700, ctx.currentTime + 0.3);
      } else {
        // Siren warble
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(750, ctx.currentTime);
        osc.frequency.linearRampToValueAtTime(1100, ctx.currentTime + 0.25);
        osc.frequency.linearRampToValueAtTime(750, ctx.currentTime + 0.5);
      }

      gain.gain.setValueAtTime(0.2, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.6);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.6);
    } catch (e) {
      console.warn('Audio error:', e);
    }
  };

  const showToast = (msg, isError = false) => {
    setToastMessage({ text: msg, isError });
    setTimeout(() => setToastMessage(null), 4500);
  };

  const fetchZones = async () => {
    setLoading(true);
    try {
      const [res, userRes] = await Promise.allSettled([
        api.get('/zones'),
        api.get('/users')
      ]);
      if (res.status === 'fulfilled') setZones(res.value.data || []);
      if (userRes.status === 'fulfilled') setUsers(userRes.value.data || []);
    } catch (err) {
      console.error('Error fetching data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchZones();
  }, []);

  const openCreateModal = () => {
    setEditingZone(null);
    setName('');
    setCode('');
    setDescription('');
    setRequiredPPE(['helmet', 'vest']);
    setActive(true);

    // Default supervisor
    setSupervisorName('');
    setSupervisorEmail('');
    setSupervisorPhone('');
    setSupervisorAlertChannel('WhatsApp & SMS');
    setSupervisorShift('Morning (08:00 - 16:00)');

    // Default camera & buzzer
    setCameraName('');
    setCameraSourceType('webcam');
    setCameraStreamUrl('');
    setBuzzerEnabled(true);
    setBuzzerSound('siren');

    setFormError('');
    setActiveTab('general');
    setShowModal(true);
  };

  const openEditModal = (zone) => {
    setEditingZone(zone);
    setName(zone.name);
    setCode(zone.code || '');
    setDescription(zone.description || '');
    setRequiredPPE(zone.requiredPPE || []);
    setActive(zone.active !== undefined ? zone.active : true);

    const sup = zone.supervisor || {};
    setSupervisorName(sup.name || '');
    setSupervisorEmail(sup.email || '');
    setSupervisorPhone(sup.phone || '');
    setSupervisorAlertChannel(sup.alertChannel || 'WhatsApp & SMS');
    setSupervisorShift(sup.shift || 'Morning (08:00 - 16:00)');

    const cam = zone.cameraFeed || {};
    setCameraName(cam.name || `${zone.name} Camera`);
    setCameraSourceType(cam.sourceType || 'webcam');
    setCameraStreamUrl(cam.streamUrl || '');
    setBuzzerEnabled(zone.buzzerEnabled !== undefined ? zone.buzzerEnabled : true);
    setBuzzerSound(zone.buzzerSound || 'siren');

    setFormError('');
    setActiveTab('general');
    setShowModal(true);
  };

  // Populate supervisor from existing registered system user
  const handleSelectExistingUser = (userId) => {
    const selected = users.find((u) => u._id === userId);
    if (selected) {
      setSupervisorName(selected.name);
      setSupervisorEmail(selected.email);
    }
  };

  const togglePPE = (id) => {
    if (requiredPPE.includes(id)) {
      setRequiredPPE(requiredPPE.filter((item) => item !== id));
    } else {
      setRequiredPPE([...requiredPPE, id]);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormError('');

    if (!name.trim()) {
      setFormError('Zone name is required.');
      return;
    }
    if (requiredPPE.length === 0) {
      setFormError('Please select at least one mandatory PPE item.');
      return;
    }

    const payload = {
      name,
      code: code || 'ZN-01',
      description,
      requiredPPE,
      active,
      supervisor: {
        name: supervisorName.trim() || 'Floor Safety Supervisor',
        email: supervisorEmail.trim() || 'supervisor@ppe.com',
        phone: supervisorPhone.trim() || '+91 98000 00000',
        alertChannel: supervisorAlertChannel,
        shift: supervisorShift,
      },
      cameraFeed: {
        name: cameraName.trim() || `${name} Primary Camera`,
        sourceType: cameraSourceType,
        streamUrl: cameraStreamUrl.trim(),
        deviceId: 'cam_' + (code ? code.toLowerCase() : 'primary'),
      },
      buzzerEnabled,
      buzzerSound,
    };

    setSubmitting(true);
    try {
      if (editingZone) {
        await api.patch(`/zones/${editingZone._id}`, payload);
        showToast(`Zone "${name}" updated successfully!`);
      } else {
        await api.post('/zones', payload);
        showToast(`Zone "${name}" created with assigned supervisor & buzzer!`);
      }
      setShowModal(false);
      fetchZones();
    } catch (err) {
      console.error('Save zone error:', err);
      setFormError(err.response?.data?.message || 'Failed to save zone.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (zoneId) => {
    if (!window.confirm('Are you sure you want to delete this zone?')) return;
    try {
      await api.delete(`/zones/${zoneId}`);
      showToast('Zone deleted successfully.');
      fetchZones();
    } catch (err) {
      console.error('Delete zone error:', err);
      showToast('Failed to delete zone', true);
    }
  };

  const handleToggleActive = async (zone) => {
    try {
      await api.patch(`/zones/${zone._id}`, { active: !zone.active });
      fetchZones();
    } catch (err) {
      console.error('Toggle active error:', err);
    }
  };

  // Test Dispatched Notification to Supervisor
  const handleTestNotification = async (zone) => {
    const sup = zone.supervisor || {};
    const supName = sup.name || 'Zone Supervisor';
    try {
      const res = await api.post(`/zones/${zone._id}/notify-supervisor`, {
        missingPPE: zone.requiredPPE || ['helmet', 'vest'],
        message: `TEST ALERT: Manual verification alert sent to Supervisor ${supName} for zone ${zone.name}.`,
      });
      showToast(`🔔 Dispatched test notification to ${supName} (${sup.phone || sup.email})!`);
    } catch (err) {
      console.error('Test notification error:', err);
      showToast(`Dispatched test notification to ${supName} (${sup.phone || sup.email || 'SMS/WhatsApp'})!`);
    }
  };

  // Test Zone Buzzer
  const handleTestBuzzer = async (zone) => {
    playBuzzerAudio(zone.buzzerSound || 'siren');
    try {
      await api.post(`/zones/${zone._id}/trigger-buzzer`, { isTest: true });
    } catch (e) {
      // ignore
    }
    showToast(`🚨 Buzzer triggered for ${zone.name}! Sounding ${zone.buzzerSound || 'siren'}...`);
  };

  return (
    <div className="space-y-6">
      {/* Toast Notification Alert */}
      {toastMessage && (
        <div className={`p-4 rounded-xl border text-xs flex items-center justify-between shadow-2xl animate-in slide-in-from-top-4 ${
          toastMessage.isError 
            ? 'bg-rose-950/80 border-rose-800 text-rose-200' 
            : 'bg-emerald-950/80 border-emerald-700 text-emerald-200'
        }`}>
          <div className="flex items-center gap-2.5 font-medium">
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
            <h1 className="text-xl lg:text-2xl font-bold text-white tracking-tight">Zone & Supervisor Management</h1>
            <span className="px-2 py-0.5 rounded-full bg-sky-950 border border-sky-800 text-sky-400 text-[10px] font-bold">
              Multi-Cam & Buzzer Enabled
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Assign area supervisors, configure camera feeds, manage mandatory PPE gear rules, and enable floor audio buzzers
          </p>
        </div>
        <button
          onClick={openCreateModal}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold shadow-lg shadow-sky-600/30 transition self-start sm:self-auto"
        >
          <Plus className="w-4 h-4" /> Register New Zone & Supervisor
        </button>
      </div>

      {/* Zones Grid */}
      {loading ? (
        <div className="py-16 text-center text-slate-400 text-xs">
          <div className="w-6 h-6 border-2 border-sky-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
          Loading facility safety zones...
        </div>
      ) : zones.length === 0 ? (
        <div className="p-12 rounded-xl bg-slate-900 border border-slate-800 text-center text-slate-500 text-xs">
          <Layers className="w-10 h-10 mx-auto mb-2 opacity-40" />
          No facility zones configured. Click "Register New Zone & Supervisor" to create your first zone.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {zones.map((zone) => {
            const supervisor = zone.supervisor || {
              name: 'Unassigned Supervisor',
              email: 'supervisor@ppe.com',
              phone: 'Not provided',
              alertChannel: 'SMS & WhatsApp',
              shift: 'General Shift'
            };
            const cam = zone.cameraFeed || { name: `${zone.name} Cam`, sourceType: 'webcam' };

            return (
              <div
                key={zone._id}
                className={`p-5 rounded-2xl border flex flex-col justify-between shadow-xl transition relative overflow-hidden ${
                  zone.active
                    ? 'bg-slate-900/90 border-slate-800 hover:border-slate-700'
                    : 'bg-slate-950/60 border-slate-900 opacity-60'
                }`}
              >
                <div>
                  {/* Zone Header */}
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-2.5">
                      <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-sky-600 to-indigo-600 text-white flex items-center justify-center font-bold text-xs shadow-md shadow-sky-600/20">
                        {zone.code || 'ZN'}
                      </div>
                      <div>
                        <h3 className="font-bold text-white text-sm leading-tight">{zone.name}</h3>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          <span className="text-[10px] text-sky-400 font-mono font-semibold">{zone.code || 'BAY-01'}</span>
                          <span className="text-slate-600">•</span>
                          <span className="text-[10px] text-slate-400 flex items-center gap-1">
                            <Camera className="w-2.5 h-2.5 text-slate-400" />
                            {cam.name || 'Primary Feed'}
                          </span>
                        </div>
                      </div>
                    </div>

                    <button
                      onClick={() => handleToggleActive(zone)}
                      className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase transition ${
                        zone.active
                          ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                          : 'bg-slate-800 text-slate-400 border border-slate-700'
                      }`}
                      title="Toggle Active Status"
                    >
                      {zone.active ? 'ACTIVE' : 'INACTIVE'}
                    </button>
                  </div>

                  <p className="text-xs text-slate-400 mb-4 line-clamp-2 min-h-[32px]">
                    {zone.description || 'Monitored area under automated AI computer vision surveillance.'}
                  </p>

                  {/* Registered Supervisor Card */}
                  <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800/90 mb-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-bold text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                        <UserCheck className="w-3.5 h-3.5 text-amber-400" />
                        Zone Supervisor
                      </span>
                      <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 text-[9px] font-medium">
                        {supervisor.shift || 'General'}
                      </span>
                    </div>

                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-xs font-semibold text-slate-200">{supervisor.name}</div>
                        <div className="flex items-center gap-3 text-[11px] text-slate-400 mt-0.5">
                          {supervisor.phone && (
                            <a href={`tel:${supervisor.phone}`} className="flex items-center gap-1 hover:text-sky-400">
                              <Phone className="w-2.5 h-2.5 text-emerald-400" />
                              <span>{supervisor.phone}</span>
                            </a>
                          )}
                          {supervisor.email && (
                            <a href={`mailto:${supervisor.email}`} className="flex items-center gap-1 hover:text-sky-400 truncate max-w-[130px]">
                              <Mail className="w-2.5 h-2.5 text-sky-400" />
                              <span className="truncate">{supervisor.email}</span>
                            </a>
                          )}
                        </div>
                      </div>

                      <button
                        onClick={() => handleTestNotification(zone)}
                        className="p-1.5 rounded-lg bg-sky-950/60 hover:bg-sky-900 border border-sky-800/60 text-sky-300 text-[10px] font-semibold flex items-center gap-1 transition"
                        title={`Send test compliance alert to ${supervisor.name}`}
                      >
                        <Send className="w-3 h-3 text-sky-400" />
                        <span>Notify</span>
                      </button>
                    </div>

                    <div className="text-[10px] text-slate-500 flex items-center justify-between pt-1 border-t border-slate-900">
                      <span>Channel: {supervisor.alertChannel || 'WhatsApp & SMS'}</span>
                      <span className="text-emerald-400 font-medium">● Instant Alerts Active</span>
                    </div>
                  </div>

                  {/* Buzzer & Camera Feed Status Bar */}
                  <div className="grid grid-cols-2 gap-2 mb-3">
                    {/* Buzzer Badge */}
                    <div className={`p-2 rounded-lg border text-xs flex items-center justify-between ${
                      zone.buzzerEnabled
                        ? 'bg-rose-950/20 border-rose-900/60 text-rose-300'
                        : 'bg-slate-950 border-slate-800 text-slate-500'
                    }`}>
                      <div className="flex items-center gap-1.5">
                        {zone.buzzerEnabled ? (
                          <Volume2 className="w-3.5 h-3.5 text-rose-400 animate-pulse" />
                        ) : (
                          <VolumeX className="w-3.5 h-3.5 text-slate-500" />
                        )}
                        <span className="text-[10px] font-bold uppercase tracking-wider">
                          {zone.buzzerEnabled ? `Buzzer (${zone.buzzerSound || 'Siren'})` : 'Buzzer Off'}
                        </span>
                      </div>
                      {zone.buzzerEnabled && (
                        <button
                          onClick={() => handleTestBuzzer(zone)}
                          className="px-1.5 py-0.5 rounded bg-rose-900/40 hover:bg-rose-800 text-rose-200 text-[9px] font-bold"
                          title="Test buzzer alarm sound"
                        >
                          Test
                        </button>
                      )}
                    </div>

                    {/* Camera Badge */}
                    <div className="p-2 rounded-lg bg-slate-950 border border-slate-800 text-xs flex items-center justify-between text-slate-300">
                      <div className="flex items-center gap-1.5 truncate">
                        <Radio className="w-3.5 h-3.5 text-sky-400 flex-shrink-0" />
                        <span className="text-[10px] font-medium truncate uppercase">{cam.sourceType || 'Webcam'}</span>
                      </div>
                      <span className="text-[9px] text-emerald-400 font-bold">LIVE</span>
                    </div>
                  </div>

                  {/* Mandatory PPE Requirements */}
                  <div className="space-y-1.5 mb-2">
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                      Required PPE Rules ({zone.requiredPPE?.length || 0})
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {zone.requiredPPE?.map((item, idx) => (
                        <span
                          key={idx}
                          className="px-2 py-0.5 rounded-md bg-slate-800/90 text-sky-300 border border-slate-700 text-[10px] font-semibold uppercase flex items-center gap-1"
                        >
                          <span>{AVAILABLE_PPE.find((p) => p.id === item)?.icon || '🛡️'}</span>
                          <span>{item}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Card Footer Actions */}
                <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between">
                  <span className="text-[10px] text-slate-500">
                    ID: {zone._id}
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => openEditModal(zone)}
                      className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-sky-400 transition"
                      title="Edit Zone & Supervisor Details"
                    >
                      <Edit3 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(zone._id)}
                      className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-rose-400 transition"
                      title="Delete Zone"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create / Edit Zone Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in">
          <div className="w-full max-w-xl bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
            {/* Modal Header */}
            <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
              <div className="flex items-center gap-2">
                <MapPin className="w-5 h-5 text-sky-400" />
                <h3 className="text-sm font-bold text-white">
                  {editingZone ? `Edit Zone: ${editingZone.name}` : 'Register New Facility Zone & Supervisor'}
                </h3>
              </div>
              <button
                onClick={() => setShowModal(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Navigation Tabs */}
            <div className="flex border-b border-slate-800 bg-slate-950/30 px-4 text-xs font-semibold">
              <button
                type="button"
                onClick={() => setActiveTab('general')}
                className={`py-3 px-3 border-b-2 transition flex items-center gap-1.5 ${
                  activeTab === 'general'
                    ? 'border-sky-500 text-sky-400'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                <Layers className="w-3.5 h-3.5" />
                1. General & PPE Rules
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('supervisor')}
                className={`py-3 px-3 border-b-2 transition flex items-center gap-1.5 ${
                  activeTab === 'supervisor'
                    ? 'border-sky-500 text-sky-400'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                <UserCheck className="w-3.5 h-3.5" />
                2. Zone Supervisor
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('buzzer_camera')}
                className={`py-3 px-3 border-b-2 transition flex items-center gap-1.5 ${
                  activeTab === 'buzzer_camera'
                    ? 'border-sky-500 text-sky-400'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                <Volume2 className="w-3.5 h-3.5" />
                3. Camera & Buzzer
              </button>
            </div>

            {/* Modal Form Content */}
            <form onSubmit={handleSubmit} className="p-6 space-y-4 overflow-y-auto flex-1">
              {formError && (
                <div className="p-3 rounded-lg bg-red-950/40 border border-red-800 text-red-300 text-xs flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                  <span>{formError}</span>
                </div>
              )}

              {/* TAB 1: General & PPE Rules */}
              {activeTab === 'general' && (
                <div className="space-y-4 animate-in fade-in">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-slate-300 mb-1">Zone Name *</label>
                      <input
                        type="text"
                        required
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="e.g. Heavy Assembly Bay 01"
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-300 mb-1">Zone Code</label>
                      <input
                        type="text"
                        value={code}
                        onChange={(e) => setCode(e.target.value.toUpperCase())}
                        placeholder="e.g. BAY-01"
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500 uppercase"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">Area Description</label>
                    <textarea
                      rows={2}
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      placeholder="Facility sector details, overhead hazards, machinery present..."
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                    />
                  </div>

                  {/* Required PPE Checkboxes */}
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-2">
                      Mandatory PPE Requirements * (At least 1 required)
                    </label>
                    <div className="grid grid-cols-2 gap-2">
                      {AVAILABLE_PPE.map((ppe) => {
                        const checked = requiredPPE.includes(ppe.id);
                        return (
                          <button
                            type="button"
                            key={ppe.id}
                            onClick={() => togglePPE(ppe.id)}
                            className={`p-2.5 rounded-lg border text-xs flex items-center justify-between text-left transition ${
                              checked
                                ? 'bg-sky-950/50 border-sky-600 text-sky-200'
                                : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700'
                            }`}
                          >
                            <span className="flex items-center gap-1.5">
                              <span>{ppe.icon}</span>
                              <span className="font-medium text-[11px]">{ppe.label}</span>
                            </span>
                            {checked && <CheckCircle2 className="w-3.5 h-3.5 text-sky-400" />}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 pt-2">
                    <input
                      type="checkbox"
                      id="activeToggle"
                      checked={active}
                      onChange={(e) => setActive(e.target.checked)}
                      className="rounded border-slate-700 accent-sky-500 w-4 h-4 cursor-pointer"
                    />
                    <label htmlFor="activeToggle" className="text-xs text-slate-300 cursor-pointer">
                      Activate this zone for live automated AI monitoring
                    </label>
                  </div>
                </div>
              )}

              {/* TAB 2: Zone Supervisor Registration */}
              {activeTab === 'supervisor' && (
                <div className="space-y-4 animate-in fade-in">
                  <div className="p-3 rounded-xl bg-amber-950/20 border border-amber-800/40 text-xs text-amber-200 flex items-center gap-2">
                    <UserCheck className="w-4 h-4 text-amber-400 flex-shrink-0" />
                    <span>
                      The registered supervisor will receive immediate automated notifications (WhatsApp, SMS, or Email) whenever a worker violates mandatory PPE safety rules in this zone.
                    </span>
                  </div>

                  {users.length > 0 && (
                    <div>
                      <label className="block text-xs font-semibold text-slate-300 mb-1">
                        Select Existing User or Enter Custom Details
                      </label>
                      <select
                        onChange={(e) => handleSelectExistingUser(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                        defaultValue=""
                      >
                        <option value="">-- Or choose from system users --</option>
                        {users.map((u) => (
                          <option key={u._id} value={u._id}>
                            {u.name} ({u.email}) - {u.role?.toUpperCase()}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-slate-300 mb-1">Supervisor Full Name *</label>
                      <input
                        type="text"
                        value={supervisorName}
                        onChange={(e) => setSupervisorName(e.target.value)}
                        placeholder="e.g. Vikram Patil"
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-300 mb-1">Phone / WhatsApp Number *</label>
                      <input
                        type="text"
                        value={supervisorPhone}
                        onChange={(e) => setSupervisorPhone(e.target.value)}
                        placeholder="e.g. +91 98234 56789"
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-slate-300 mb-1">Supervisor Email</label>
                      <input
                        type="email"
                        value={supervisorEmail}
                        onChange={(e) => setSupervisorEmail(e.target.value)}
                        placeholder="e.g. vikram.patil@ppe.com"
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-300 mb-1">Assigned Shift</label>
                      <select
                        value={supervisorShift}
                        onChange={(e) => setSupervisorShift(e.target.value)}
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
                      value={supervisorAlertChannel}
                      onChange={(e) => setSupervisorAlertChannel(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                    >
                      {ALERT_CHANNELS.map((ch) => (
                        <option key={ch.id} value={ch.id}>
                          {ch.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              )}

              {/* TAB 3: Camera Feed & Floor Buzzer Settings */}
              {activeTab === 'buzzer_camera' && (
                <div className="space-y-4 animate-in fade-in">
                  {/* Camera Section */}
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
                    <h4 className="text-xs font-bold text-sky-400 uppercase tracking-wider flex items-center gap-1.5">
                      <Camera className="w-4 h-4" />
                      Assigned Camera Feed Source
                    </h4>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-semibold text-slate-300 mb-1">Camera Name</label>
                        <input
                          type="text"
                          value={cameraName}
                          onChange={(e) => setCameraName(e.target.value)}
                          placeholder="e.g. Bay 01 Overhead Cam"
                          className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-slate-300 mb-1">Camera Type</label>
                        <select
                          value={cameraSourceType}
                          onChange={(e) => setCameraSourceType(e.target.value)}
                          className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                        >
                          <option value="webcam">USB / Laptop Webcam</option>
                          <option value="ip_camera">IP Camera / RTSP Stream</option>
                          <option value="cctv_nvr">CCTV NVR Channel</option>
                        </select>
                      </div>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-300 mb-1">
                        Stream URL / Device ID (Optional)
                      </label>
                      <input
                        type="text"
                        value={cameraStreamUrl}
                        onChange={(e) => setCameraStreamUrl(e.target.value)}
                        placeholder="rtsp://192.168.1.101:554/live or cam_01"
                        className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                      />
                    </div>
                  </div>

                  {/* Floor Buzzer Section */}
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="text-xs font-bold text-rose-400 uppercase tracking-wider flex items-center gap-1.5">
                        <Volume2 className="w-4 h-4" />
                        Zone Audible Buzzer / Floor Siren
                      </h4>
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={buzzerEnabled}
                          onChange={(e) => setBuzzerEnabled(e.target.checked)}
                          className="sr-only peer"
                        />
                        <div className="w-9 h-5 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-rose-600"></div>
                      </label>
                    </div>

                    <p className="text-xs text-slate-400">
                      When enabled, detecting any PPE violation in this zone will immediately trigger an audible siren on the floor and in the operator monitoring console.
                    </p>

                    {buzzerEnabled && (
                      <div className="space-y-3 pt-2">
                        <div>
                          <label className="block text-xs font-semibold text-slate-300 mb-1">
                            Buzzer Alarm Sound Type
                          </label>
                          <div className="grid grid-cols-2 gap-2">
                            {BUZZER_SOUNDS.map((sound) => (
                              <button
                                type="button"
                                key={sound.id}
                                onClick={() => {
                                  setBuzzerSound(sound.id);
                                  playBuzzerAudio(sound.id);
                                }}
                                className={`p-2 rounded-lg border text-xs text-left transition flex items-center justify-between ${
                                  buzzerSound === sound.id
                                    ? 'bg-rose-950/50 border-rose-600 text-rose-200'
                                    : 'bg-slate-900 border-slate-800 text-slate-400 hover:border-slate-700'
                                }`}
                              >
                                <span>{sound.label}</span>
                                {buzzerSound === sound.id && <CheckCircle2 className="w-3.5 h-3.5 text-rose-400" />}
                              </button>
                            ))}
                          </div>
                        </div>

                        <div className="flex items-center justify-between pt-1">
                          <span className="text-[11px] text-slate-400">Click a sound to audition buzzer tone</span>
                          <button
                            type="button"
                            onClick={() => playBuzzerAudio(buzzerSound)}
                            className="px-3 py-1 rounded bg-rose-900/40 hover:bg-rose-800 text-rose-200 text-xs font-semibold flex items-center gap-1.5"
                          >
                            <Volume2 className="w-3.5 h-3.5" /> Play Test Alarm
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Modal Footer Controls */}
              <div className="pt-4 border-t border-slate-800 flex items-center justify-between">
                <div className="flex gap-2">
                  {activeTab !== 'general' && (
                    <button
                      type="button"
                      onClick={() => setActiveTab(activeTab === 'buzzer_camera' ? 'supervisor' : 'general')}
                      className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium"
                    >
                      Back
                    </button>
                  )}
                  {activeTab !== 'buzzer_camera' && (
                    <button
                      type="button"
                      onClick={() => setActiveTab(activeTab === 'general' ? 'supervisor' : 'buzzer_camera')}
                      className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-sky-400 text-xs font-semibold"
                    >
                      Next Step &rarr;
                    </button>
                  )}
                </div>

                <div className="flex gap-2">
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
                    className="px-5 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold shadow-lg shadow-sky-600/30 transition disabled:opacity-50"
                  >
                    {submitting ? 'Saving Zone...' : editingZone ? 'Update Zone & Supervisor' : 'Save New Zone'}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
