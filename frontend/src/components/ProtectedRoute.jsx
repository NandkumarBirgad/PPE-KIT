import React from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Loader2 } from 'lucide-react';

export default function ProtectedRoute({ allowedRoles }) {
  const { user, loading, isAuthenticated } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center text-slate-400 gap-3">
        <Loader2 className="w-8 h-8 animate-spin text-sky-500" />
        <span className="text-sm font-medium tracking-wide">Validating security session...</span>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles) {
    const rawRole = (user?.role || '').trim().toUpperCase();
    const isSuperAdmin = ['SUPER_ADMIN', 'ADMIN', 'SUPERADMIN'].includes(rawRole);
    const isSupervisor = ['ZONE_SUPERVISOR', 'SUPERVISOR', 'REVIEWER'].includes(rawRole);

    const isAllowed = allowedRoles.some((r) => {
      const normR = r.trim().toUpperCase();
      if (normR === 'SUPER_ADMIN' || normR === 'ADMIN') return isSuperAdmin;
      if (normR === 'ZONE_SUPERVISOR' || normR === 'SUPERVISOR') return isSupervisor || isSuperAdmin;
      return normR === rawRole;
    });

    if (!isAllowed) {
      if (isSuperAdmin) {
        return <Navigate to="/admin/dashboard" replace />;
      }
      return <Navigate to="/supervisor/dashboard" replace />;
    }
  }

  return <Outlet />;
}

