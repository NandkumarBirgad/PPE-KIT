import React, { useState, useEffect } from 'react';
import { 
  Camera, 
  Plus, 
  Edit3, 
  Trash2, 
  CheckCircle2, 
  X, 
  AlertTriangle, 
  Radio, 
  MapPin, 
  RefreshCw, 
  Power,
  Tv,
  Layers,
  ExternalLink
} from 'lucide-react';
import { Link } from 'react-router-dom';
import api from '../services/api';

export default function CameraManagementPage() {
  const [cameras, setCameras] = useState([]);
  const [zones, setZones] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingCamera, setEditingCamera] = useState(null);
  const [toastMessage, setToastMessage] = useState(null);

  // Form State
  const [name, setName] = useState('');
  const [zoneId, setZoneId] = useState('');
  const [sourceType, setSourceType] = useState('webcam');
  const [streamUrl, setStreamUrl] = useState('');
  const [resolution, setResolution] = useState('1080p HD');
  const [fps, setFps] = useState(25);
  const [location, setLocation] = useState('');
  const [status, setStatus] = useState('ONLINE');
  const [formError, setFormError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const showToast = (text, isError = false) => {
    setToastMessage({ text, isError });
    setTimeout(() => setToastMessage(null), 4000);
  };

  const fetchData = async () => {
    setLoading(true);
    try {
      const [camRes, zoneRes] = await Promise.allSettled([
        api.get('/cameras'),
        api.get('/zones'),
      ]);
      if (camRes.status === 'fulfilled') setCameras(camRes.value.data || []);
      if (zoneRes.status === 'fulfilled') {
        const activeZones = zoneRes.value.data || [];
        setZones(activeZones);
        if (activeZones.length > 0 && !zoneId) {
          setZoneId(activeZones[0]._id);
        }
      }
    } catch (err) {
      console.error('Fetch cameras error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const openCreateModal = () => {
    setEditingCamera(null);
    setName('');
    setZoneId(zones.length > 0 ? zones[0]._id : '');
    setSourceType('webcam');
    setStreamUrl('');
    setResolution('1080p HD');
    setFps(25);
    setLocation('');
    setStatus('ONLINE');
    setFormError('');
    setShowModal(true);
  };

  const openEditModal = (cam) => {
    setEditingCamera(cam);
    setName(cam.name || '');
    setZoneId(cam.zoneId || (zones.length > 0 ? zones[0]._id : ''));
    setSourceType(cam.sourceType || 'webcam');
    setStreamUrl(cam.streamUrl || '');
    setResolution(cam.resolution || '1080p HD');
    setFps(cam.fps || 25);
    setLocation(cam.location || '');
    setStatus(cam.status || 'ONLINE');
    setFormError('');
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormError('');

    if (!name.trim()) {
      setFormError('Camera name is required.');
      return;
    }

    const selectedZone = zones.find((z) => String(z._id) === String(zoneId));
    const payload = {
      name: name.trim(),
      zoneId,
      zoneName: selectedZone ? selectedZone.name : 'General Monitored Zone',
      sourceType,
      streamUrl: streamUrl.trim(),
      resolution,
      fps: Number(fps),
      location: location.trim() || 'Facility Sector',
      status,
    };

    setSubmitting(true);
    try {
      if (editingCamera) {
        await api.patch(`/cameras/${editingCamera._id}`, payload);
        showToast(`Camera "${name}" updated successfully!`);
      } else {
        await api.post('/cameras', payload);
        showToast(`Camera "${name}" registered successfully!`);
      }
      setShowModal(false);
      fetchData();
    } catch (err) {
      console.error('Save camera error:', err);
      setFormError(err.response?.data?.message || 'Failed to save camera.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Are you sure you want to delete this camera feed?')) return;
    try {
      await api.delete(`/cameras/${id}`);
      showToast('Camera deleted successfully.');
      fetchData();
    } catch (err) {
      console.error('Delete camera error:', err);
      showToast('Failed to delete camera', true);
    }
  };

  const [testingCameraId, setTestingCameraId] = useState(null);

  const handleTestConnection = async (cam) => {
    setTestingCameraId(cam._id);
    try {
      const res = await api.post(`/cameras/${cam._id}/test-connection`);
      showToast(res.data?.message || 'Camera connection verified', !res.data?.success);
    } catch (err) {
      showToast(err.response?.data?.message || 'Failed to ping camera feed', true);
    } finally {
      setTestingCameraId(null);
    }
  };

  const handleToggleStatus = async (cam) => {
    try {
      const res = await api.post(`/cameras/${cam._id}/toggle-status`);
      showToast(res.data?.message || 'Camera status updated');
      fetchData();
    } catch (err) {
      console.error('Toggle status error:', err);
    }
  };

  return (
    <div className="space-y-6">
      {/* Toast Notification */}
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
            <h1 className="text-xl lg:text-2xl font-bold text-white tracking-tight">Camera Feed Governance</h1>
            <span className="px-2 py-0.5 rounded-full bg-sky-950 border border-sky-800 text-sky-400 text-[10px] font-bold">
              {cameras.length} Active Feeds
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Configure CCTV streams, assign cameras to safety sectors, manage RTSP endpoints, and monitor feed connectivity
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <Link
            to="/admin/live"
            className="flex items-center gap-2 px-3.5 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-200 text-xs font-semibold border border-slate-700 transition"
          >
            <Tv className="w-4 h-4 text-sky-400" />
            <span>Live Surveillance HUD</span>
          </Link>
          <button
            onClick={openCreateModal}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold shadow-lg shadow-sky-600/30 transition"
          >
            <Plus className="w-4 h-4" />
            <span>Add CCTV Camera</span>
          </button>
        </div>
      </div>

      {/* Camera Grid */}
      {loading ? (
        <div className="py-16 text-center text-slate-400 text-xs">
          <div className="w-6 h-6 border-2 border-sky-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
          Loading CCTV camera infrastructure...
        </div>
      ) : cameras.length === 0 ? (
        <div className="p-12 rounded-2xl bg-slate-900 border border-slate-800 text-center text-slate-500 text-xs">
          <Camera className="w-10 h-10 mx-auto mb-2 opacity-40" />
          No cameras configured. Click "Add CCTV Camera" to provision your first feed.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {cameras.map((cam) => (
            <div
              key={cam._id}
              className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl flex flex-col justify-between hover:border-slate-700 transition"
            >
              <div>
                {/* Header */}
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2.5">
                    <div className="w-9 h-9 rounded-xl bg-sky-950 border border-sky-800 text-sky-400 flex items-center justify-center font-bold text-xs">
                      <Camera className="w-4 h-4" />
                    </div>
                    <div>
                      <h3 className="font-bold text-white text-sm leading-tight">{cam.name}</h3>
                      <span className="text-[10px] text-slate-400 font-mono mt-0.5 block">{cam.resolution} • {cam.fps} FPS</span>
                    </div>
                  </div>

                  <button
                    onClick={() => handleToggleStatus(cam)}
                    className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase transition ${
                      cam.status === 'ONLINE'
                        ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                        : 'bg-rose-950 text-rose-400 border border-rose-800'
                    }`}
                    title="Toggle Camera Online/Offline"
                  >
                    {cam.status}
                  </button>
                </div>

                {/* Stream / Zone Metadata Card */}
                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80 mb-4 space-y-2 text-xs">
                  <div className="flex items-center justify-between text-slate-400">
                    <span className="text-[10px] font-semibold uppercase tracking-wider flex items-center gap-1">
                      <MapPin className="w-3 h-3 text-sky-400" /> Assigned Zone:
                    </span>
                    <span className="text-slate-200 font-semibold">{cam.zoneName}</span>
                  </div>

                  <div className="flex items-center justify-between text-slate-400">
                    <span className="text-[10px] font-semibold uppercase tracking-wider flex items-center gap-1">
                      <Radio className="w-3 h-3 text-emerald-400" /> Source Type:
                    </span>
                    <span className="text-slate-300 font-mono text-[11px] uppercase">{cam.sourceType}</span>
                  </div>

                  {cam.streamUrl && (
                    <div className="text-[10px] text-slate-400 pt-1 border-t border-slate-800 truncate font-mono">
                      Endpoint: {cam.streamUrl}
                    </div>
                  )}

                  <div className="text-[10px] text-slate-500 pt-1 border-t border-slate-800">
                    Location: {cam.location || 'Facility Deck'}
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="pt-3 border-t border-slate-800 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Link
                    to="/admin/live"
                    className="text-xs text-sky-400 hover:text-sky-300 font-semibold flex items-center gap-1"
                  >
                    <ExternalLink className="w-3 h-3" />
                    <span>Live Stream</span>
                  </Link>

                  <button
                    onClick={() => handleTestConnection(cam)}
                    disabled={testingCameraId === cam._id}
                    className="text-[11px] text-slate-400 hover:text-emerald-400 font-medium flex items-center gap-1 transition"
                    title="Ping and verify live camera feed"
                  >
                    <Radio className={`w-3 h-3 ${testingCameraId === cam._id ? 'animate-pulse text-amber-400' : 'text-slate-400'}`} />
                    <span>{testingCameraId === cam._id ? 'Pinging...' : 'Test Feed'}</span>
                  </button>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => openEditModal(cam)}
                    className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-sky-400 transition"
                    title="Edit Camera"
                  >
                    <Edit3 className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleDelete(cam._id)}
                    className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-rose-400 transition"
                    title="Delete Camera"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add / Edit Camera Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in">
          <div className="w-full max-w-lg bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Camera className="w-4 h-4 text-sky-400" />
                {editingCamera ? `Edit Camera: ${editingCamera.name}` : 'Provision New CCTV Camera Feed'}
              </h3>
              <button
                onClick={() => setShowModal(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              {formError && (
                <div className="p-3 rounded-lg bg-red-950/40 border border-red-800 text-red-300 text-xs flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                  <span>{formError}</span>
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Camera Name *</label>
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Bay 01 Overhead HD"
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Assigned Zone *</label>
                  <select
                    value={zoneId}
                    onChange={(e) => setZoneId(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                  >
                    {zones.map((z) => (
                      <option key={z._id} value={z._id}>
                        {z.name} ({z.code || 'ZONE'})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Source Type</label>
                  <select
                    value={sourceType}
                    onChange={(e) => setSourceType(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                  >
                    <option value="webcam">USB / Laptop Webcam</option>
                    <option value="ip_camera">IP Camera (RTSP / HTTP)</option>
                    <option value="cctv_nvr">NVR / DVR CCTV Stream</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Resolution</label>
                  <select
                    value={resolution}
                    onChange={(e) => setResolution(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                  >
                    <option value="1080p HD">1080p HD (1920x1080)</option>
                    <option value="720p HD">720p HD (1280x720)</option>
                    <option value="4K UHD">4K Ultra HD (3840x2160)</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  RTSP Stream URL / Device ID
                </label>
                <input
                  type="text"
                  value={streamUrl}
                  onChange={(e) => setStreamUrl(e.target.value)}
                  placeholder="rtsp://admin:pass@192.168.1.101:554/ch01"
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500 font-mono"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Physical Location</label>
                  <input
                    type="text"
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                    placeholder="e.g. Scaffolding Beam 4"
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Initial Status</label>
                  <select
                    value={status}
                    onChange={(e) => setStatus(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                  >
                    <option value="ONLINE">ONLINE (Active)</option>
                    <option value="OFFLINE">OFFLINE (Standby)</option>
                  </select>
                </div>
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
                  className="px-5 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold shadow-lg shadow-sky-600/30 transition disabled:opacity-50"
                >
                  {submitting ? 'Saving...' : editingCamera ? 'Update Camera' : 'Provision Camera'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
