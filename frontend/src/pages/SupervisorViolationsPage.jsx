import React, { useState, useEffect } from 'react';
import { 
  AlertTriangle, 
  CheckCircle2, 
  Clock, 
  Search, 
  Filter, 
  RefreshCw, 
  Eye, 
  Check, 
  X,
  MapPin,
  Calendar
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';

export default function SupervisorViolationsPage() {
  const { user } = useAuth();
  const [violations, setViolations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [reviewFilter, setReviewFilter] = useState('');
  const [search, setSearch] = useState('');
  const [selectedViolation, setSelectedViolation] = useState(null);
  const [reviewNotes, setReviewNotes] = useState('');
  const [submittingReview, setSubmittingReview] = useState(false);
  const [toastMessage, setToastMessage] = useState('');

  const fetchViolations = async () => {
    setLoading(true);
    try {
      const zoneQuery = user?.assignedZoneName ? `&search=${encodeURIComponent(user.assignedZoneName)}` : '';
      const filterParam = reviewFilter ? `&reviewStatus=${reviewFilter}` : '';
      const res = await api.get(`/detections?complianceStatus=VIOLATION${zoneQuery}${filterParam}`);
      setViolations(res.data?.events || []);
    } catch (err) {
      console.error('Fetch violations error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchViolations();
  }, [reviewFilter]);

  const handleOpenReviewModal = (v) => {
    setSelectedViolation(v);
    setReviewNotes(v.reviewerNotes || `Reviewed by Zone Supervisor ${user?.name || ''}`);
  };

  const handleSaveReview = async (newStatus) => {
    if (!selectedViolation) return;
    setSubmittingReview(true);
    try {
      await api.patch(`/detections/${selectedViolation._id}/review`, {
        reviewStatus: newStatus,
        reviewerNotes: reviewNotes.trim(),
      });
      setToastMessage(`Incident review updated to ${newStatus}`);
      setSelectedViolation(null);
      fetchViolations();
      setTimeout(() => setToastMessage(''), 4000);
    } catch (err) {
      console.error('Review update error:', err);
    } finally {
      setSubmittingReview(false);
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
          <button onClick={() => setToastMessage('')} className="text-slate-400 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl lg:text-2xl font-bold text-white tracking-tight">Zone Safety Violations Log</h1>
            <span className="px-2 py-0.5 rounded-full bg-emerald-950 border border-emerald-800 text-emerald-400 text-[10px] font-bold">
              {user?.assignedZoneName || 'My Zone'}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Review, acknowledge, and resolve workplace PPE safety breaches detected in your sector
          </p>
        </div>

        <button
          onClick={fetchViolations}
          className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-200 text-xs font-semibold border border-slate-700 transition self-start sm:self-auto"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh Violations</span>
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
            placeholder="Search missing gear or notes..."
            className="w-full bg-slate-950 border border-slate-700 rounded-xl pl-9 pr-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <Filter className="w-4 h-4 text-slate-400" />
          <select
            value={reviewFilter}
            onChange={(e) => setReviewFilter(e.target.value)}
            className="bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
          >
            <option value="">All Review Statuses</option>
            <option value="PENDING">Pending Review</option>
            <option value="APPROVED">Acknowledged / Approved</option>
            <option value="REJECTED">False Positive / Rejected</option>
          </select>
        </div>
      </div>

      {/* Violations Table */}
      <div className="rounded-2xl bg-slate-900 border border-slate-800 shadow-xl overflow-hidden">
        {loading ? (
          <div className="py-16 text-center text-slate-400 text-xs">
            <div className="w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
            Loading sector violations...
          </div>
        ) : violations.length === 0 ? (
          <div className="py-16 text-center text-slate-500 text-xs">
            <CheckCircle2 className="w-10 h-10 mx-auto mb-2 text-emerald-500/50" />
            No safety violations found for your sector.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] font-bold border-b border-slate-800">
                <tr>
                  <th className="p-3.5">Worker (कोणाचा)</th>
                  <th className="p-3.5">Zone & Location (कोठून)</th>
                  <th className="p-3.5">Camera Feed</th>
                  <th className="p-3.5">Missing PPE Equipment</th>
                  <th className="p-3.5">Review Status</th>
                  <th className="p-3.5">Timestamp</th>
                  <th className="p-3.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-medium">
                {violations.map((v) => (
                  <tr key={v._id} className="hover:bg-slate-800/30 transition">
                    <td className="p-3.5">
                      <div className="font-bold text-amber-300">
                        {v.workerTag || v.personId || 'Worker #1'}
                      </div>
                      <div className="text-[10px] text-slate-500 font-mono">
                        {v.personId ? `Target: ${v.personId}` : 'Tracked Body'}
                      </div>
                    </td>
                    <td className="p-3.5">
                      <div className="font-bold text-slate-100">{v.zoneName}</div>
                      <div className="text-[10px] text-slate-400">{v.location || 'Floor Line'}</div>
                    </td>
                    <td className="p-3.5 font-mono text-[11px] text-sky-400">
                      {v.cameraName || 'Deck Camera'}
                    </td>
                    <td className="p-3.5">
                      <span className="px-2 py-0.5 rounded bg-rose-950/80 border border-rose-800 text-rose-300 text-[10px] font-bold">
                        {v.missingPPE?.join(', ') || 'Mandatory PPE'}
                      </span>
                    </td>
                    <td className="p-3.5">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                        v.reviewStatus === 'APPROVED'
                          ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                          : v.reviewStatus === 'REJECTED'
                          ? 'bg-slate-800 text-slate-400'
                          : 'bg-amber-950 text-amber-300 border border-amber-800'
                      }`}>
                        {v.reviewStatus || 'PENDING'}
                      </span>
                    </td>
                    <td className="p-3.5 font-mono text-[11px] text-slate-400">
                      {v.createdAt ? new Date(v.createdAt).toLocaleString() : 'Just now'}
                    </td>
                    <td className="p-3.5 text-right">
                      <button
                        onClick={() => handleOpenReviewModal(v)}
                        className="px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-sky-300 text-xs font-semibold border border-slate-700 transition cursor-pointer"
                      >
                        Review
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Review Modal */}
      {selectedViolation && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in">
          <div className="w-full max-w-lg bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-rose-400" />
                Review Safety Incident Details
              </h3>
              <button
                onClick={() => setSelectedViolation(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-6 space-y-4 text-xs">
              {selectedViolation.evidenceImageReference && (
                <div className="aspect-video rounded-xl overflow-hidden bg-black border border-slate-800">
                  <img
                    src={selectedViolation.evidenceImageReference}
                    alt="Violation Evidence"
                    className="w-full h-full object-contain"
                  />
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 text-[10px] uppercase font-bold block mb-1">
                    👤 Worker (कोणाचा)
                  </span>
                  <div className="font-bold text-amber-300">
                    {selectedViolation.workerTag || selectedViolation.personId || 'Worker #1'}
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 text-[10px] uppercase font-bold block mb-1">
                    📍 Location (कोठून)
                  </span>
                  <div className="font-bold text-white">
                    {selectedViolation.zoneName}
                  </div>
                  <span className="text-[10px] text-slate-400 block">
                    {selectedViolation.location || selectedViolation.cameraName}
                  </span>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Supervisor Notes / Corrective Actions Taken
                </label>
                <textarea
                  rows={3}
                  value={reviewNotes}
                  onChange={(e) => setReviewNotes(e.target.value)}
                  placeholder="e.g. Worker instructed to wear helmet immediately. Incident resolved."
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>

              <div className="pt-3 border-t border-slate-800 flex items-center justify-between gap-2">
                <button
                  type="button"
                  onClick={() => setSelectedViolation(null)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold"
                >
                  Cancel
                </button>

                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={submittingReview}
                    onClick={() => handleSaveReview('REJECTED')}
                    className="px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold border border-slate-700"
                  >
                    Mark False Positive
                  </button>
                  <button
                    type="button"
                    disabled={submittingReview}
                    onClick={() => handleSaveReview('APPROVED')}
                    className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold shadow-lg shadow-emerald-600/30"
                  >
                    Acknowledge & Close
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
