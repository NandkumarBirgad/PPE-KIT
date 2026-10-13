import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { HardHat, ShieldCheck, Lock, Mail, AlertCircle, ArrowRight, Building2, Shield, Eye, Flame, Award } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function LoginPage() {
  const [email, setEmail] = useState('admin@ppe.com');
  const [password, setPassword] = useState('Admin@123');
  const [plantSite, setPlantSite] = useState('pune_unit4');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const { login } = useAuth();
  const navigate = useNavigate();

  const executeLogin = async (targetEmail, targetPass) => {
    setError('');
    setLoading(true);

    try {
      const loggedInUser = await login(targetEmail, targetPass);
      if (loggedInUser?.role === 'SUPER_ADMIN' || loggedInUser?.role === 'admin') {
        navigate('/admin/dashboard');
      } else {
        navigate('/supervisor/dashboard');
      }
    } catch (err) {
      console.error('Login error:', err);
      if (err.code === 'ERR_NETWORK' || !err.response) {
        setError('Backend API Server (http://localhost:5000) शी संपर्क होत नाही. कृपया run_system.bat किंवा backend app.py चालू असल्याची खात्री करा.');
      } else {
        setError(err.response?.data?.message || 'Authentication failed. Please verify credentials.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    executeLogin(email, password);
  };

  const handleDemoClick = (demoEmail, demoPass) => {
    setEmail(demoEmail);
    setPassword(demoPass);
    executeLogin(demoEmail, demoPass);
  };

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4 relative overflow-hidden industrial-grid">
      {/* Background radial glow */}
      <div className="absolute w-[600px] h-[600px] bg-sky-600/10 rounded-full blur-3xl pointer-events-none -top-48 -left-48"></div>
      <div className="absolute w-[600px] h-[600px] bg-amber-500/10 rounded-full blur-3xl pointer-events-none -bottom-48 -right-48"></div>

      <div className="max-w-md w-full bg-slate-900/95 border border-slate-800 rounded-3xl shadow-2xl p-6 sm:p-8 relative z-10 backdrop-blur-2xl">
        {/* Top Hazard Accent Bar */}
        <div className="absolute top-0 left-0 right-0 h-1.5 hazard-stripes rounded-t-3xl"></div>

        {/* Brand header */}
        <div className="flex flex-col items-center text-center mt-2 mb-6">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-amber-500 to-amber-600 flex items-center justify-center text-slate-950 shadow-xl shadow-amber-500/25 mb-4 ring-4 ring-amber-500/15">
            <HardHat className="w-9 h-9" />
          </div>
          <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-slate-800/80 border border-slate-700/80 text-[10px] font-bold text-amber-400 font-mono uppercase tracking-wider mb-2">
            <Building2 className="w-3 h-3" /> Industrial EHS Safety Suite
          </div>
          <h1 className="text-2xl font-black text-white tracking-tight">PPE Compliance Monitor</h1>
          <p className="text-xs text-slate-400 mt-1">
            Plant-floor AI surveillance & role-based safety governance portal
          </p>
        </div>

        {error && (
          <div className="mb-5 p-3 rounded-xl bg-red-950/40 border border-red-800/60 text-red-300 text-xs flex items-center gap-2.5">
            <AlertCircle className="w-4 h-4 flex-shrink-0 text-red-400" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Facility Plant Selector */}
          <div>
            <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">
              Operating Facility / Plant Site
            </label>
            <div className="relative">
              <Building2 className="w-4 h-4 text-slate-500 absolute left-3.5 top-3" />
              <select
                value={plantSite}
                onChange={(e) => setPlantSite(e.target.value)}
                className="w-full bg-slate-950/80 border border-slate-800 rounded-xl pl-10 pr-3.5 py-2.5 text-xs text-slate-200 focus:outline-none focus:ring-2 focus:ring-sky-500 transition cursor-pointer font-medium"
              >
                <option value="pune_unit4">Plant Unit 04 - Pune Heavy Fab & Assembly</option>
                <option value="gujarat_unit2">Plant Unit 02 - Gujarat Stamping Shop</option>
                <option value="chennai_unit1">Plant Unit 01 - Chennai Robotic Paint Cell</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">
              Workstation Email ID
            </label>
            <div className="relative">
              <Mail className="w-4 h-4 text-slate-500 absolute left-3.5 top-3" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.com"
                className="w-full bg-slate-950/80 border border-slate-800 rounded-xl pl-10 pr-3.5 py-2.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-sky-500 transition"
              />
            </div>
          </div>

          <div>
            <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">
              Security Key / Password
            </label>
            <div className="relative">
              <Lock className="w-4 h-4 text-slate-500 absolute left-3.5 top-3" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full bg-slate-950/80 border border-slate-800 rounded-xl pl-10 pr-3.5 py-2.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-sky-500 transition"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 px-4 rounded-xl bg-sky-600 hover:bg-sky-500 text-white font-bold text-xs shadow-lg shadow-sky-600/30 flex items-center justify-center gap-2 transition disabled:opacity-60 cursor-pointer mt-2"
          >
            {loading ? (
              <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
            ) : (
              <>
                <span>Authenticate & Access Command Center</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </form>

        {/* Quick Demo Access Credentials */}
        <div className="mt-6 pt-5 border-t border-slate-800/80">
          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2.5 text-center font-mono">
            Direct Access Test Accounts
          </p>
          <div className="space-y-2 text-xs">
            <button
              type="button"
              onClick={() => handleDemoClick('admin@ppe.com', 'Admin@123')}
              className="w-full p-2.5 rounded-xl bg-slate-950/80 hover:bg-slate-800 border border-slate-800 flex items-center justify-between text-left transition cursor-pointer"
            >
              <div>
                <div className="font-bold text-amber-400 text-xs">Super Admin (EHS Plant Director)</div>
                <div className="text-[10px] text-slate-400 font-mono">admin@ppe.com • Admin@123</div>
              </div>
              <span className="text-[10px] px-2 py-0.5 rounded bg-amber-950 text-amber-300 font-bold border border-amber-800 font-mono">
                1-Click Login &rarr;
              </span>
            </button>

            <button
              type="button"
              onClick={() => handleDemoClick('supervisor@ppe.com', 'Supervisor@123')}
              className="w-full p-2.5 rounded-xl bg-slate-950/80 hover:bg-slate-800 border border-slate-800 flex items-center justify-between text-left transition cursor-pointer"
            >
              <div>
                <div className="font-bold text-emerald-400 text-xs">Zone Supervisor (Bay-01 Marshal)</div>
                <div className="text-[10px] text-slate-400 font-mono">supervisor@ppe.com • Supervisor@123</div>
              </div>
              <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 font-bold border border-emerald-800 font-mono">
                1-Click Login &rarr;
              </span>
            </button>
          </div>
        </div>

        {/* Regulatory Badges Footer */}
        <div className="mt-6 pt-4 border-t border-slate-800/60 flex items-center justify-center gap-4 text-[10px] text-slate-500 font-mono">
          <span className="flex items-center gap-1">
            <Award className="w-3 h-3 text-sky-400" /> ISO 45001:2018
          </span>
          <span>•</span>
          <span className="flex items-center gap-1">
            <Shield className="w-3 h-3 text-emerald-400" /> OSHA 1910 Subpart I
          </span>
        </div>
      </div>
    </div>
  );
}
