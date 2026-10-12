import React, { useState, useEffect } from 'react';
import { 
  ShieldCheck, 
  ShieldAlert, 
  HelpCircle, 
  Activity, 
  TrendingUp, 
  TrendingDown, 
  Users, 
  Calendar,
  AlertTriangle,
  ArrowUpRight,
  RefreshCw,
  HardHat,
  Eye
} from 'lucide-react';
import { 
  AreaChart, 
  Area, 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  Legend
} from 'recharts';
import api from '../services/api';
import { Link } from 'react-router-dom';

export default function DashboardPage() {
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState({
    totalEvents: 0,
    compliantEvents: 0,
    violationEvents: 0,
    uncertainEvents: 0,
    complianceRate: 0,
    monitoredPersons: 0,
  });
  const [trends, setTrends] = useState([]);
  const [zoneSummary, setZoneSummary] = useState([]);
  const [recentViolations, setRecentViolations] = useState([]);

  const fetchDashboardData = async () => {
    setLoading(true);
    try {
      const [sumRes, trendRes, zoneRes, violRes] = await Promise.allSettled([
        api.get('/dashboard/summary'),
        api.get('/dashboard/trends'),
        api.get('/dashboard/zone-summary'),
        api.get('/detections?complianceStatus=VIOLATION&limit=5'),
      ]);

      if (sumRes.status === 'fulfilled') setSummary(sumRes.value.data);
      if (trendRes.status === 'fulfilled') setTrends(trendRes.value.data.trends || []);
      if (zoneRes.status === 'fulfilled') setZoneSummary(zoneRes.value.data.zones || []);
      if (violRes.status === 'fulfilled') setRecentViolations(violRes.value.data.events || []);
    } catch (err) {
      console.error('Error fetching dashboard data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl lg:text-2xl font-bold text-white tracking-tight">Compliance Intelligence Dashboard</h1>
          <p className="text-xs text-slate-400 mt-1">Real-time workplace safety posture and PPE adherence metrics</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchDashboardData}
            disabled={loading}
            className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh Feed
          </button>
          <Link
            to="/live"
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold shadow-lg shadow-sky-600/20 transition"
          >
            <HardHat className="w-3.5 h-3.5" />
            Launch Live Camera
          </Link>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Compliance Rate */}
        <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 shadow-xl relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Overall Compliance</span>
            <div className="w-9 h-9 rounded-lg bg-emerald-950/60 border border-emerald-800/40 flex items-center justify-center text-emerald-400">
              <ShieldCheck className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-white">
              {summary.complianceRate ? `${summary.complianceRate}%` : '0%'}
            </span>
            <span className="text-xs text-emerald-400 font-semibold flex items-center">
              <TrendingUp className="w-3 h-3 mr-0.5" /> Healthy
            </span>
          </div>
          <div className="w-full bg-slate-800 h-1.5 rounded-full mt-3 overflow-hidden">
            <div
              className="bg-emerald-500 h-full rounded-full transition-all duration-500"
              style={{ width: `${summary.complianceRate || 0}%` }}
            ></div>
          </div>
        </div>

        {/* Total Events */}
        <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 shadow-xl">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Total Inspections</span>
            <div className="w-9 h-9 rounded-lg bg-sky-950/60 border border-sky-800/40 flex items-center justify-center text-sky-400">
              <Activity className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-white">{summary.totalEvents}</span>
            <span className="text-xs text-slate-400">recorded events</span>
          </div>
          <div className="text-[11px] text-slate-500 mt-3 flex justify-between">
            <span>Compliant: <b className="text-emerald-400">{summary.compliantEvents}</b></span>
            <span>Persons: <b className="text-sky-400">{summary.monitoredPersons || 0}</b></span>
          </div>
        </div>

        {/* Violations */}
        <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 shadow-xl">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Safety Violations</span>
            <div className="w-9 h-9 rounded-lg bg-rose-950/60 border border-rose-800/40 flex items-center justify-center text-rose-400">
              <ShieldAlert className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-white">{summary.violationEvents}</span>
            <span className="text-xs text-rose-400 font-semibold flex items-center">
              Requires Action
            </span>
          </div>
          <div className="text-[11px] text-slate-500 mt-3 flex justify-between">
            <span>Pending Review: <b className="text-rose-400">{summary.violationEvents}</b></span>
            <Link to="/violations" className="text-sky-400 hover:underline flex items-center gap-0.5">
              Inspect <ArrowUpRight className="w-3 h-3" />
            </Link>
          </div>
        </div>

        {/* Uncertain / Incomplete */}
        <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 shadow-xl">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Uncertain / Review</span>
            <div className="w-9 h-9 rounded-lg bg-amber-950/60 border border-amber-800/40 flex items-center justify-center text-amber-400">
              <HelpCircle className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-white">{summary.uncertainEvents}</span>
            <span className="text-xs text-amber-400 font-semibold">Low confidence</span>
          </div>
          <div className="text-[11px] text-slate-500 mt-3">
            Partial occlusion or distance threshold
          </div>
        </div>
      </div>

      {/* Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Daily Compliance Trend */}
        <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 shadow-xl">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-sm font-bold text-white">7-Day Compliance Trajectory</h2>
              <p className="text-xs text-slate-400">Trend of compliant vs. non-compliant detection events</p>
            </div>
            <Calendar className="w-4 h-4 text-slate-500" />
          </div>

          <div className="h-64">
            {trends.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-slate-500 text-xs">
                <Activity className="w-8 h-8 mb-2 opacity-40" />
                No historical trend data yet. Start live monitoring or upload media.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trends}>
                  <defs>
                    <linearGradient id="compliantGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.4}/>
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                    </linearGradient>
                    <linearGradient id="violationGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#ef4444" stopOpacity={0.4}/>
                      <stop offset="95%" stopColor="#ef4444" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="date" stroke="#64748b" fontSize={11} />
                  <YAxis stroke="#64748b" fontSize={11} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px', fontSize: '12px' }}
                  />
                  <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '10px' }} />
                  <Area type="monotone" dataKey="compliant" name="Compliant" stroke="#10b981" fillOpacity={1} fill="url(#compliantGrad)" strokeWidth={2} />
                  <Area type="monotone" dataKey="violation" name="Violations" stroke="#ef4444" fillOpacity={1} fill="url(#violationGrad)" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Zone-Wise Adherence */}
        <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 shadow-xl">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-sm font-bold text-white">Zone-Wise Adherence Index</h2>
              <p className="text-xs text-slate-400">Total violations detected per active facility zone</p>
            </div>
            <Users className="w-4 h-4 text-slate-500" />
          </div>

          <div className="h-64">
            {zoneSummary.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-slate-500 text-xs">
                <AlertTriangle className="w-8 h-8 mb-2 opacity-40" />
                No zone events recorded. Configure zones in Zone Management.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={zoneSummary}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="name" stroke="#64748b" fontSize={11} />
                  <YAxis stroke="#64748b" fontSize={11} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px', fontSize: '12px' }}
                  />
                  <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '10px' }} />
                  <Bar dataKey="compliant" name="Compliant" fill="#10b981" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="violations" name="Violations" fill="#ef4444" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      {/* Recent Violations Table */}
      <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-sm font-bold text-white">Recent Compliance Breaches</h2>
            <p className="text-xs text-slate-400">Real-time alerts requiring supervisor safety sign-off</p>
          </div>
          <Link
            to="/violations"
            className="text-xs text-sky-400 hover:text-sky-300 font-semibold flex items-center gap-1"
          >
            View Full Incident Ledger <ArrowUpRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {recentViolations.length === 0 ? (
          <div className="py-8 text-center text-slate-500 text-xs">
            <ShieldCheck className="w-9 h-9 mx-auto mb-2 text-emerald-500/50" />
            No recent violations logged. Workplace safety compliance is 100%.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/60 text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="py-3 px-4 font-semibold">Timestamp</th>
                  <th className="py-3 px-4 font-semibold">Zone</th>
                  <th className="py-3 px-4 font-semibold">Missing PPE</th>
                  <th className="py-3 px-4 font-semibold">Source</th>
                  <th className="py-3 px-4 font-semibold">Status</th>
                  <th className="py-3 px-4 font-semibold text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {recentViolations.map((v) => (
                  <tr key={v._id} className="hover:bg-slate-800/30 transition">
                    <td className="py-3 px-4 text-slate-300">
                      {new Date(v.timestamp || v.createdAt).toLocaleString()}
                    </td>
                    <td className="py-3 px-4 font-medium text-white">{v.zoneName || 'General Area'}</td>
                    <td className="py-3 px-4">
                      <div className="flex flex-wrap gap-1">
                        {v.missingPPE && v.missingPPE.length > 0 ? (
                          v.missingPPE.map((ppe, i) => (
                            <span
                              key={i}
                              className="px-2 py-0.5 rounded text-[10px] font-semibold bg-rose-950/60 text-rose-300 border border-rose-800/50 uppercase"
                            >
                              {ppe}
                            </span>
                          ))
                        ) : (
                          <span className="text-slate-500">None</span>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4 capitalize text-slate-400">{v.sourceType || 'Webcam'}</td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-950 text-rose-400 border border-rose-800 uppercase">
                        {v.complianceStatus}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right">
                      <Link
                        to="/violations"
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-sky-400 font-medium transition"
                      >
                        <Eye className="w-3 h-3" /> Review
                      </Link>
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
