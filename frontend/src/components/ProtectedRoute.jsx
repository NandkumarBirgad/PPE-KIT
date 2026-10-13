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
    const userRole = user?.role;
    const isAllowed = allowedRoles.includes(userRole) || 
      (allowedRoles.includes('SUPER_ADMIN') && userRole === 'admin') ||
      (allowedRoles.includes('ZONE_SUPERVISOR') && ['supervisor', 'reviewer'].includes(userRole));

    if (!isAllowed) {
      if (userRole === 'SUPER_ADMIN' || userRole === 'admin') {
        return <Navigate to="/admin/dashboard" replace />;
      }
      return <Navigate to="/supervisor/dashboard" replace />;
    }
  }

  return <Outlet />;
}

