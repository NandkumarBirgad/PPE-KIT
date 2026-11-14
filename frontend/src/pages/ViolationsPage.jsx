import React, { useState, useEffect } from 'react';
import { 
  AlertTriangle, 
  Search, 
  Filter, 
  Eye, 
  CheckCircle2, 
  XCircle, 
  Clock, 
  ChevronLeft, 
  ChevronRight,
  ShieldAlert,
  HelpCircle,
  FileText,
  X,
  ExternalLink
} from 'lucide-react';
import api from '../services/api';
import AuthenticatedImage from '../components/AuthenticatedImage';
import {
  CANONICAL_STATES,
  getIncidentCanonicalState,
  getIncidentResolutionType,
  getResolutionTypeLabel,
  getIncidentStatusBadge,
  mapCanonicalFilterToApi,
  validateLifecycleAction
} from '../services/incidentLifecycle';

export default function ViolationsPage() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  // Filters
  const [search, setSearch] = useState('');
  const [complianceFilter, setComplianceFilter] = useState('');
  const [reviewFilter, setReviewFilter] = useState('');

  // Review modal
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [reviewNotes, setReviewNotes] = useState('');
  const [updatingReview, setUpdatingReview] = useState(false);
  const [validationError, setValidationError] = useState('');
  const [actionSuccess, setActionSuccess] = useState('');

  const fetchEvents = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page,
        limit: 10,
        search,
      });
      if (complianceFilter) params.append('complianceStatus', complianceFilter);
      const apiFilter = mapCanonicalFilterToApi(reviewFilter);
      if (apiFilter.status) params.append('status', apiFilter.status);

      const res = await api.get(`/detections?${params.toString()}`);
      setEvents(res.data.events || []);
      setTotalPages(res.data.totalPages || 1);
      setTotalCount(res.data.totalCount || 0);
    } catch (err) {
      console.error('Error fetching violation events:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEvents();
  }, [page, complianceFilter, reviewFilter]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setPage(1);
    fetchEvents();
  };

  const handleReviewAction = async (action) => {
    if (!selectedEvent) return;
    setValidationError('');
    const validation = validateLifecycleAction(action, reviewNotes);
    if (!validation.valid) {
      setValidationError(validation.error);
      return;
    }

    setUpdatingReview(true);
    try {
      const payload = { action };
      const trimmed = reviewNotes.trim();
      if (action === 'ACKNOWLEDGE') {
        if (trimmed) {
          payload.reviewerNotes = trimmed;
          payload.reason = trimmed;
        }
      } else if (action === 'RESOLVE' || action === 'FALSE_POSITIVE') {
        payload.reason = trimmed;
        if (action === 'FALSE_POSITIVE') {
          payload.resolution_type = 'FALSE_POSITIVE';
        }
      }

      await api.patch(`/detections/${selectedEvent._id}/review`, payload);

      const actionLabel = action === 'ACKNOWLEDGE'
        ? 'acknowledged (Status: ACKNOWLEDGED)'
        : (action === 'FALSE_POSITIVE' ? 'marked as false positive (Status: RESOLVED)' : 'resolved (Status: RESOLVED)');
      setActionSuccess(`Incident successfully ${actionLabel}.`);
      setSelectedEvent(null);
      setReviewNotes('');
      fetchEvents();
      setTimeout(() => setActionSuccess(''), 4000);
    } catch (err) {
      console.error('Error updating review:', err);
      const errMsg = err.response?.data?.message || 'Failed to update lifecycle status.';
      setValidationError(errMsg);
    } finally {
      setUpdatingReview(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Toast Alert */}
      {actionSuccess && (
        <div className="p-3.5 rounded-xl bg-emerald-950/80 border border-emerald-800 text-emerald-200 text-xs flex items-center justify-between shadow-xl">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>{actionSuccess}</span>
          </div>
          <button onClick={() => setActionSuccess('')} className="text-slate-400 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl lg:text-2xl font-bold text-white tracking-tight">PPE Violations & Incidents Ledger</h1>
          <p className="text-xs text-slate-400 mt-1">Audit log of optical PPE violations, compliance evaluations, and safety incidents</p>
        </div>
        <div className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-300">
          Total Safety Incidents: <span className="text-sky-400 font-mono font-bold">{totalCount}</span>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex flex-wrap items-center justify-between gap-4">
        <form onSubmit={handleSearchSubmit} className="flex items-center gap-2 flex-1 min-w-[240px]">
          <div className="relative w-full max-w-sm">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search by zone or PPE item..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg pl-9 pr-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-sky-500"
            />
          </div>
          <button
            type="submit"
            className="px-3 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold transition"
          >
            Search
          </button>
        </form>

        <div className="flex items-center gap-3">
          <select
            value={complianceFilter}
            onChange={(e) => { setComplianceFilter(e.target.value); setPage(1); }}
            className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-300 focus:outline-none"
          >
            <option value="">All Compliance Statuses</option>
            <option value="VIOLATION">PPE Violations Only</option>
            <option value="UNCERTAIN">Uncertain Only</option>
            <option value="COMPLIANT">Compliant</option>
          </select>

          <select
            value={reviewFilter}
            onChange={(e) => { setReviewFilter(e.target.value); setPage(1); }}
            className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-300 focus:outline-none"
          >
            <option value="">All Lifecycle Statuses</option>
            <option value="OPEN">Open Incidents</option>
            <option value="ACKNOWLEDGED">Acknowledged Incidents</option>
            <option value="RESOLVED">Resolved Incidents</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="rounded-xl bg-slate-900 border border-slate-800 shadow-xl overflow-hidden">
        {loading ? (
          <div className="py-16 text-center text-slate-400 text-xs">
            <div className="w-6 h-6 border-2 border-sky-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
            Loading incident ledger...
          </div>
        ) : events.length === 0 ? (
          <div className="py-16 text-center text-slate-500 text-xs">
            <CheckCircle2 className="w-10 h-10 mx-auto mb-2 text-emerald-500/40" />
            No records matched your search criteria.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="py-3.5 px-4 font-semibold">Incident Time</th>
                  <th className="py-3.5 px-4 font-semibold">Worker / Personnel</th>
                  <th className="py-3.5 px-4 font-semibold">Zone & Location</th>
                  <th className="py-3.5 px-4 font-semibold">Camera Source</th>
                  <th className="py-3.5 px-4 font-semibold">Missing PPE</th>
                  <th className="py-3.5 px-4 font-semibold">Compliance</th>
                  <th className="py-3.5 px-4 font-semibold">Lifecycle Status</th>
                  <th className="py-3.5 px-4 font-semibold text-right">Inspect</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {events.map((e) => (
                  <tr key={e._id} className="hover:bg-slate-800/40 transition">
                    <td className="py-3.5 px-4 text-slate-300 font-mono text-[11px]">
                      {new Date(e.timestamp || e.createdAt).toLocaleString()}
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="font-bold text-amber-300">
                        {e.workerTag || e.personId || 'Worker #1'}
                      </div>
                      <div className="text-[10px] text-slate-500 font-mono">
                        {e.personId ? `Track ID: ${e.personId}` : 'Tracked Body'}
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="font-semibold text-white">{e.zoneName || 'General Zone'}</div>
                      <div className="text-[10px] text-slate-400">
                        {e.location || e.cameraName || 'Deck Sensor'}
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      <span className="font-mono text-[11px] text-sky-400">
                        {e.cameraName || e.sourceType || 'Webcam'}
                      </span>
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="flex flex-wrap gap-1">
                        {e.missingPPE && e.missingPPE.length > 0 ? (
                          e.missingPPE.map((ppe, i) => (
                            <span
                              key={i}
                              className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-950/60 text-rose-300 border border-rose-800/50 uppercase"
                            >
                              {ppe}
                            </span>
                          ))
                        ) : (
                          <span className="text-slate-500">None</span>
                        )}
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase border ${
                        e.complianceStatus === 'COMPLIANT'
                          ? 'bg-emerald-950 text-emerald-400 border-emerald-800'
                          : e.complianceStatus === 'VIOLATION'
                          ? 'bg-rose-950 text-rose-400 border-rose-800'
                          : 'bg-amber-950 text-amber-400 border-amber-800'
                      }`}>
                        {e.complianceStatus}
                      </span>
                    </td>
                    <td className="py-3.5 px-4">
                      {(() => {
                        const badge = getIncidentStatusBadge(e);
                        return (
                          <span className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${badge.badgeClass}`}>
                            {badge.label} {badge.subLabel ? `(${badge.subLabel})` : ''}
                          </span>
                        );
                      })()}
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <button
                        onClick={() => {
                          setSelectedEvent(e);
                          setValidationError('');
                          setReviewNotes(e.reviewerNotes || e.resolution_reason || '');
                        }}
                        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-sky-400 font-semibold border border-slate-700 transition cursor-pointer"
                      >
                        <Eye className="w-3.5 h-3.5" /> Details
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination footer */}
        <div className="p-4 bg-slate-950/80 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
          <span>
            Page <b className="text-white">{page}</b> of <b className="text-white">{totalPages}</b>
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(p - 1, 1))}
              disabled={page <= 1}
              className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-40 transition"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => setPage((p) => Math.min(p + 1, totalPages))}
              disabled={page >= totalPages}
              className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-40 transition"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Review & Details Modal */}
      {selectedEvent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in">
          <div className="w-full max-w-2xl bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
            {/* Modal Header */}
            <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-amber-400" />
                <h3 className="text-sm font-bold text-white">Incident Forensic Inspection</h3>
              </div>
              <button
                onClick={() => setSelectedEvent(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-4">
              {/* Evidence Snapshot */}
              {selectedEvent.evidenceImageReference && (
                <div className="rounded-xl overflow-hidden border border-slate-800 bg-black aspect-video flex items-center justify-center">
                  <AuthenticatedImage
                    src={selectedEvent.evidenceImageReference}
                    alt="Forensic Evidence"
                    className="w-full h-full object-contain"
                  />
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 text-[10px] uppercase font-bold block mb-1">
                    👤 Worker Identity
                  </span>
                  <div className="font-bold text-amber-300 text-sm">
                    {selectedEvent.workerTag || selectedEvent.personId || 'Tracked Worker #1'}
                  </div>
                  <span className="text-[10px] text-slate-500 font-mono">
                    {selectedEvent.personId ? `Target: ${selectedEvent.personId}` : 'AI Optical Tracking'}
                  </span>
                </div>

                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 text-[10px] uppercase font-bold block mb-1">
                    📍 Zone & Location
                  </span>
                  <div className="font-bold text-white text-sm">
                    {selectedEvent.zoneName || 'Heavy Assembly Bay 01'}
                  </div>
                  <span className="text-[10px] text-slate-400 block mt-0.5">
                    {selectedEvent.location || selectedEvent.cameraName || 'Deck Column #4'}
                  </span>
                </div>

                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 text-[10px] uppercase font-bold block mb-1">
                    📹 Camera Feed Source
                  </span>
                  <div className="font-mono text-sky-400 font-semibold">
                    {selectedEvent.cameraName || selectedEvent.sourceType || 'Optical CCTV Stream'}
                  </div>
                  <span className="text-[10px] text-slate-500">
                    Camera ID: {selectedEvent.cameraId || 'cam_01'}
                  </span>
                </div>

                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 text-[10px] uppercase font-bold block mb-1">
                    🕒 Incident Time & Supervisor
                  </span>
                  <div className="font-mono text-white text-[11px]">
                    {new Date(selectedEvent.timestamp || selectedEvent.createdAt).toLocaleString()}
                  </div>
                  <span className="text-[10px] text-emerald-400 block mt-0.5">
                    Supervisor: {selectedEvent.supervisorName || 'Floor Safety Officer'}
                  </span>
                </div>
              </div>

              {/* Current Lifecycle Status Banner */}
              {(() => {
                const canonicalState = getIncidentCanonicalState(selectedEvent);
                const resType = getIncidentResolutionType(selectedEvent);
                const isResolved = canonicalState === 'RESOLVED';
                const isAcknowledged = canonicalState === 'ACKNOWLEDGED';
                const isOpen = canonicalState === 'OPEN';

                return (
                  <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between text-xs">
                    <div>
                      <span className="text-slate-400 text-[10px] uppercase font-bold block mb-0.5">
                        Current Lifecycle Status
                      </span>
                      <div className="flex items-center gap-2">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                          isOpen ? 'bg-amber-950 text-amber-300 border border-amber-800'
                          : isAcknowledged ? 'bg-sky-950 text-sky-300 border border-sky-800'
                          : 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                        }`}>
                          {canonicalState}
                        </span>
                        {isResolved && resType && (
                          <span className="text-[11px] text-slate-400">
                            via <b className="text-slate-200">{getResolutionTypeLabel(resType)}</b>
                          </span>
                        )}
                      </div>
                    </div>
                    {selectedEvent.resolved_at && (
                      <span className="text-[10px] font-mono text-slate-500">
                        Resolved: {new Date(selectedEvent.resolved_at).toLocaleString()}
                      </span>
                    )}
                  </div>
                );
              })()}

              {/* Missing PPE */}
              <div className="p-3 rounded-lg bg-rose-950/20 border border-rose-800/40 text-xs">
                <span className="font-bold text-rose-300 block mb-1">Violations / Missing PPE:</span>
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {selectedEvent.missingPPE?.length > 0 ? (
                    selectedEvent.missingPPE.map((p, i) => (
                      <span key={i} className="px-2 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800 text-[10px] font-bold uppercase">
                        {p}
                      </span>
                    ))
                  ) : (
                    <span className="text-slate-400">None</span>
                  )}
                </div>
              </div>

              {validationError && (
                <div className="p-3 rounded-xl bg-rose-950/80 border border-rose-800 text-rose-200 text-xs flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                  <span>{validationError}</span>
                </div>
              )}

              {/* Review Notes Input */}
              {(() => {
                const canonicalState = getIncidentCanonicalState(selectedEvent);
                const isResolved = canonicalState === 'RESOLVED';

                return (
                  <div className="space-y-1.5">
                    <label className="block text-xs font-semibold text-slate-300">
                      {isResolved ? 'Recorded Resolution Reason / Notes' : 'Supervisor Notes & Mandatory Resolution Reason'}
                    </label>
                    <textarea
                      rows={3}
                      value={reviewNotes}
                      onChange={(e) => {
                        setReviewNotes(e.target.value);
                        if (validationError) setValidationError('');
                      }}
                      disabled={isResolved || updatingReview}
                      placeholder={isResolved ? 'No notes recorded.' : 'Enter resolution details or acknowledgement notes (mandatory for Resolve / False Positive)...'}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg p-3 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:opacity-60"
                    />
                  </div>
                );
              })()}
            </div>

            {/* Modal Actions */}
            {(() => {
              const canonicalState = getIncidentCanonicalState(selectedEvent);
              const isResolved = canonicalState === 'RESOLVED';
              const isOpen = canonicalState === 'OPEN';

              return (
                <div className="p-4 bg-slate-950/80 border-t border-slate-800 flex items-center justify-between">
                  <span className="text-xs text-slate-400">
                    Current state: <b className="text-white uppercase">{canonicalState}</b>
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setSelectedEvent(null)}
                      className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold cursor-pointer"
                    >
                      {isResolved ? 'Close' : 'Cancel'}
                    </button>

                    {!isResolved && (
                      <>
                        <button
                          type="button"
                          disabled={updatingReview}
                          onClick={() => handleReviewAction('FALSE_POSITIVE')}
                          className="px-3.5 py-2 rounded-lg bg-amber-950/80 hover:bg-amber-900 border border-amber-800 text-amber-200 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                        >
                          Mark False Positive
                        </button>

                        {isOpen && (
                          <button
                            type="button"
                            disabled={updatingReview}
                            onClick={() => handleReviewAction('ACKNOWLEDGE')}
                            className="px-3.5 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold shadow transition cursor-pointer disabled:opacity-50"
                          >
                            Acknowledge
                          </button>
                        )}

                        <button
                          type="button"
                          disabled={updatingReview}
                          onClick={() => handleReviewAction('RESOLVE')}
                          className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-lg shadow-emerald-600/30 transition cursor-pointer disabled:opacity-50"
                        >
                          Resolve
                        </button>
                      </>
                    )}
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      )}
    </div>
  );
}
