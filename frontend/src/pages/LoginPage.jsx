import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  HardHat, 
  ShieldCheck, 
  Lock, 
  Mail, 
  AlertCircle, 
  ArrowRight, 
  Building2, 
  Shield, 
  Eye, 
  Award,
  CheckCircle2,
  Radio,
  Zap,
  Activity,
  UserCheck
} from 'lucide-react';
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
        setError('Backend API Server (http://localhost:5000) शी संपर्क होत नाही. कृपया backend app.py चालू असल्याची खात्री करा.');
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
    <div className="min-h-screen bg-slate-100 flex flex-col justify-center py-6 px-4 sm:px-6 lg:px-8 industrial-grid">
      {/* Main Container Card */}
      <div className="max-w-6xl w-full mx-auto bg-white rounded-3xl shadow-2xl border border-blue-100 overflow-hidden grid grid-cols-1 lg:grid-cols-12 min-h-[640px]">
        
        {/* ========================================================
            LEFT COLUMN: Clear Industrial Image Showcase (58% width)
            ======================================================== */}
        <div className="lg:col-span-7 relative flex flex-col justify-between p-8 sm:p-12 overflow-hidden bg-slate-900 text-white min-h-[380px] lg:min-h-full">
          {/* Crystal Clear High-Res Image Background */}
          <div 
            className="absolute inset-0 bg-cover bg-center bg-no-repeat transition-transform duration-700 hover:scale-105"
            style={{ backgroundImage: "url('/images/factory_safety_bg.jpg')" }}
          />

          {/* Gentle Gradient for Contrast (kept light so image remains sharp and vivid) */}
          <div className="absolute inset-0 bg-gradient-to-t from-slate-950/95 via-slate-900/40 to-blue-950/40 pointer-events-none" />
          <div className="absolute top-0 left-0 right-0 h-1.5 hazard-stripes z-10"></div>

          {/* Top Brand Badges */}
          <div className="relative z-10 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2.5 px-3.5 py-1.5 rounded-xl bg-white/90 backdrop-blur-md text-slate-900 shadow-lg border border-white">
              <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold shadow-md">
                <HardHat className="w-4 h-4" />
              </div>
              <span className="font-extrabold text-sm tracking-tight text-blue-950">PPE Vision AI</span>
            </div>

            <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/90 text-white text-xs font-bold backdrop-blur-md shadow-md">
              <span className="w-2 h-2 rounded-full bg-white animate-ping"></span>
              <span>AI Surveillance Active</span>
            </div>
          </div>

          {/* Center Floating Live Telemetry Cards */}
          <div className="relative z-10 my-auto py-8 space-y-3">
            <div className="inline-block p-4 rounded-2xl bg-slate-950/75 backdrop-blur-md border border-white/20 shadow-xl max-w-md">
              <span className="text-[10px] font-mono uppercase tracking-wider text-amber-400 block mb-1 flex items-center gap-1.5 font-bold">
                <Radio className="w-3 h-3 text-amber-400 animate-pulse" /> Live Shop-Floor Protection
              </span>
              <p className="text-sm font-semibold text-white leading-snug">
                Optical AI monitors workers for Safety Helmets, High-Vis Vests & Eye Protection in real-time.
              </p>
            </div>

            {/* Quick PPE Tags */}
            <div className="flex flex-wrap gap-2 text-xs font-semibold">
              <span className="px-3 py-1 rounded-lg bg-blue-600/90 backdrop-blur-md text-white border border-blue-400/40 shadow-sm flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-blue-200" /> ⛑️ Hard Hat (99.8%)
              </span>
              <span className="px-3 py-1 rounded-lg bg-emerald-600/90 backdrop-blur-md text-white border border-emerald-400/40 shadow-sm flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-200" /> 🦺 Safety Vest (99.2%)
              </span>
              <span className="px-3 py-1 rounded-lg bg-amber-600/90 backdrop-blur-md text-white border border-amber-400/40 shadow-sm flex items-center gap-1.5">
                <Zap className="w-3.5 h-3.5 text-amber-200" /> 🚨 Auto-Buzzer Alert
              </span>
            </div>
          </div>

          {/* Bottom Plant Facility Footer */}
          <div className="relative z-10 pt-4 border-t border-white/20 flex items-center justify-between text-xs text-slate-200">
            <div className="flex items-center gap-2">
              <Building2 className="w-4 h-4 text-amber-400" />
              <span>Plant Unit 04 • Heavy Engineering Sector</span>
            </div>
            <span className="text-[11px] font-mono text-emerald-400 font-bold">ISO 45001 • OSHA 1910</span>
          </div>
        </div>

        {/* ========================================================
            RIGHT COLUMN: Easy Login & 1-Click Access (42% width)
            ======================================================== */}
        <div className="lg:col-span-5 p-8 sm:p-10 flex flex-col justify-between bg-white text-slate-900">
          <div>
            {/* Header */}
            <div className="mb-6">
              <span className="text-xs font-bold uppercase tracking-wider text-blue-600 font-mono">
                Enterprise Safety Console
              </span>
              <h1 className="text-2xl sm:text-3xl font-black text-slate-900 tracking-tight mt-1">
                Welcome Back
              </h1>
              <p className="text-xs text-slate-500 mt-1">
                Select your role below or enter credentials to enter the live command center.
              </p>
            </div>

            {/* Error Message */}
            {error && (
              <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 flex-shrink-0 text-red-600" />
                <span>{error}</span>
              </div>
            )}

            {/* QUICK 1-CLICK ACCESS BUTTONS (Ultra Clear & Fast) */}
            <div className="mb-6 space-y-2.5">
              <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider font-mono">
                ⚡ Quick 1-Click Login (झटपट प्रवेश)
              </p>

              {/* 1-Click Super Admin */}
              <button
                type="button"
                onClick={() => handleDemoClick('admin@ppe.com', 'Admin@123')}
                disabled={loading}
                className="w-full p-3 rounded-xl border-2 border-blue-200 hover:border-blue-600 bg-blue-50/70 hover:bg-blue-100/80 transition-all flex items-center justify-between group cursor-pointer text-left shadow-sm"
              >
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-blue-600 text-white flex items-center justify-center font-bold shadow-md group-hover:scale-105 transition-transform">
                    <Shield className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="text-xs font-bold text-blue-950 group-hover:text-blue-700">
                      Super Admin (सुपर अ‍ॅडमिन)
                    </div>
                    <div className="text-[10px] text-slate-500 font-mono">
                      Full Plant Control • All Cameras & Settings
                    </div>
                  </div>
                </div>
                <span className="text-[11px] font-bold px-2 py-1 rounded-md bg-blue-600 text-white shadow-sm flex items-center gap-1">
                  Enter &rarr;
                </span>
              </button>

              {/* 1-Click Zone Supervisor */}
              <button
                type="button"
                onClick={() => handleDemoClick('supervisor@ppe.com', 'Supervisor@123')}
                disabled={loading}
                className="w-full p-3 rounded-xl border-2 border-emerald-200 hover:border-emerald-600 bg-emerald-50/70 hover:bg-emerald-100/80 transition-all flex items-center justify-between group cursor-pointer text-left shadow-sm"
              >
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-emerald-600 text-white flex items-center justify-center font-bold shadow-md group-hover:scale-105 transition-transform">
                    <UserCheck className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="text-xs font-bold text-emerald-950 group-hover:text-emerald-700">
                      Zone Supervisor (झोन सुपरवायझर)
                    </div>
                    <div className="text-[10px] text-slate-500 font-mono">
                      Bay 01 Marshal • Local Buzzer & Alerts
                    </div>
                  </div>
                </div>
                <span className="text-[11px] font-bold px-2 py-1 rounded-md bg-emerald-600 text-white shadow-sm flex items-center gap-1">
                  Enter &rarr;
                </span>
              </button>
            </div>

            {/* Divider */}
            <div className="relative my-4">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-slate-200"></div>
              </div>
              <div className="relative flex justify-center text-[10px] uppercase font-mono">
                <span className="bg-white px-3 text-slate-400">or manual sign-in</span>
              </div>
            </div>

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-3">
              <div>
                <label className="block text-[11px] font-bold text-slate-700 uppercase mb-1">
                  Work Email ID
                </label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="admin@ppe.com"
                    className="w-full bg-slate-50 border border-slate-300 rounded-xl pl-10 pr-3.5 py-2 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white transition"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-bold text-slate-700 uppercase mb-1">
                  Password
                </label>
                <div className="relative">
                  <Lock className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
                  <input
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••••••"
                    className="w-full bg-slate-50 border border-slate-300 rounded-xl pl-10 pr-3.5 py-2 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white transition"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full mt-2 py-2.5 px-4 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs shadow-lg shadow-blue-600/30 flex items-center justify-center gap-2 transition cursor-pointer"
              >
                {loading ? (
                  <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                ) : (
                  <>
                    <span>Authenticate & Enter Console</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </form>
          </div>

          {/* Footer info */}
          <div className="mt-6 pt-4 border-t border-slate-100 flex items-center justify-between text-[10px] text-slate-400 font-mono">
            <span>PPE AI Vision v2.4</span>
            <span className="text-blue-600 font-semibold">ISO 45001 EHS Certified</span>
          </div>
        </div>

      </div>
    </div>
  );
}
