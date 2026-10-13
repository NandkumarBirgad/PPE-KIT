import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import AdminSidebar from './components/AdminSidebar';
import SupervisorSidebar from './components/SupervisorSidebar';
import Navbar from './components/Navbar';

// Pages
import LoginPage from './pages/LoginPage';
import AdminDashboardPage from './pages/AdminDashboardPage';
import CameraManagementPage from './pages/CameraManagementPage';
import ZoneManagementPage from './pages/ZoneManagementPage';
import SupervisorManagementPage from './pages/SupervisorManagementPage';
import ViolationsPage from './pages/ViolationsPage';
import AdminNotificationsPage from './pages/AdminNotificationsPage';
import BuzzerManagementPage from './pages/BuzzerManagementPage';
import ReportsPage from './pages/ReportsPage';
import UserManagementPage from './pages/UserManagementPage';
import SettingsPage from './pages/SettingsPage';
import LiveMonitoringPage from './pages/LiveMonitoringPage';

// Supervisor Pages
import SupervisorDashboardPage from './pages/SupervisorDashboardPage';
import SupervisorViolationsPage from './pages/SupervisorViolationsPage';
import SupervisorBuzzerPage from './pages/SupervisorBuzzerPage';
import SupervisorNotificationsPage from './pages/SupervisorNotificationsPage';

// Super Admin Layout
function AdminLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <AdminSidebar isOpen={sidebarOpen} setIsOpen={setSidebarOpen} />
      <div className="lg:pl-64 flex flex-col flex-1">
        <Navbar toggleSidebar={() => setSidebarOpen(!sidebarOpen)} />
        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

// Zone Supervisor Layout
function SupervisorLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <SupervisorSidebar isOpen={sidebarOpen} setIsOpen={setSidebarOpen} />
      <div className="lg:pl-64 flex flex-col flex-1">
        <Navbar toggleSidebar={() => setSidebarOpen(!sidebarOpen)} />
        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

// Dynamic Role-Based Redirection
function RoleRedirect() {
  const { user } = useAuth();
  if (user?.role === 'SUPER_ADMIN' || user?.role === 'admin') {
    return <Navigate to="/admin/dashboard" replace />;
  }
  return <Navigate to="/supervisor/dashboard" replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public Common Login Route */}
          <Route path="/login" element={<LoginPage />} />

          {/* Root dynamic redirect */}
          <Route element={<ProtectedRoute />}>
            <Route path="/" element={<RoleRedirect />} />
            <Route path="/dashboard" element={<RoleRedirect />} />
            <Route path="/live" element={<Navigate to="/admin/live" replace />} />
            <Route path="/violations" element={<Navigate to="/admin/violations" replace />} />
            <Route path="/zones" element={<Navigate to="/admin/zones" replace />} />
            <Route path="/settings" element={<Navigate to="/admin/settings" replace />} />
            <Route path="/reports" element={<Navigate to="/admin/reports" replace />} />
          </Route>

          {/* 1. SUPER_ADMIN Protected Routes */}
          <Route element={<ProtectedRoute allowedRoles={['SUPER_ADMIN', 'admin']} />}>
            <Route element={<AdminLayout />}>
              <Route path="/admin/dashboard" element={<AdminDashboardPage />} />
              <Route path="/admin/cameras" element={<CameraManagementPage />} />
              <Route path="/admin/zones" element={<ZoneManagementPage />} />
              <Route path="/admin/supervisors" element={<SupervisorManagementPage />} />
              <Route path="/admin/violations" element={<ViolationsPage />} />
              <Route path="/admin/notifications" element={<AdminNotificationsPage />} />
              <Route path="/admin/buzzers" element={<BuzzerManagementPage />} />
              <Route path="/admin/reports" element={<ReportsPage />} />
              <Route path="/admin/users" element={<UserManagementPage />} />
              <Route path="/admin/settings" element={<SettingsPage />} />
              <Route path="/admin/live" element={<LiveMonitoringPage />} />
            </Route>
          </Route>

          {/* 2. ZONE_SUPERVISOR Protected Routes */}
          <Route element={<ProtectedRoute allowedRoles={['ZONE_SUPERVISOR', 'supervisor', 'reviewer', 'SUPER_ADMIN', 'admin']} />}>
            <Route element={<SupervisorLayout />}>
              <Route path="/supervisor/dashboard" element={<SupervisorDashboardPage />} />
              <Route path="/supervisor/live" element={<LiveMonitoringPage />} />
              <Route path="/supervisor/violations" element={<SupervisorViolationsPage />} />
              <Route path="/supervisor/buzzers" element={<SupervisorBuzzerPage />} />
              <Route path="/supervisor/notifications" element={<SupervisorNotificationsPage />} />
            </Route>
          </Route>

          {/* Catch-all route */}
          <Route path="*" element={<RoleRedirect />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
