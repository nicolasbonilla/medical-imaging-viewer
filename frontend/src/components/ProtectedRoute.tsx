import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Loader2 } from 'lucide-react';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRole?: 'VIEWER' | 'TECHNICIAN' | 'RADIOLOGIST' | 'ADMIN';
}

/**
 * ProtectedRoute Component
 *
 * Protects routes requiring authentication and optional role-based access control.
 * Implements ISO 27001 A.9.4.1 - Information access restriction
 *
 * Features:
 * - Authentication verification
 * - Role-based access control (RBAC)
 * - Loading state handling
 * - Automatic redirect to login
 */
const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, requiredRole }) => {
  const { isAuthenticated, isLoading, user } = useAuth();

  // Show loading state while checking authentication
  if (isLoading) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-12 h-12 text-blue-500 animate-spin" />
          <p className="text-gray-400 text-lg">Verifying authentication...</p>
        </div>
      </div>
    );
  }

  // Redirect to login if not authenticated
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // Check role-based access if required
  if (requiredRole && user) {
    const roleHierarchy = {
      VIEWER: 0,
      TECHNICIAN: 1,
      RADIOLOGIST: 2,
      ADMIN: 3,
    };

    const userRoleLevel = roleHierarchy[user.role];
    const requiredRoleLevel = roleHierarchy[requiredRole];

    // User must have at least the required role level
    if (userRoleLevel < requiredRoleLevel) {
      return (
        <div className="h-screen w-screen flex items-center justify-center bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900">
          <div className="max-w-md p-8 bg-white/10 backdrop-blur-lg rounded-2xl border border-white/20 text-center">
            <h2 className="text-2xl font-bold text-white mb-4">Access Denied</h2>
            <p className="text-gray-300 mb-6">
              You don't have sufficient permissions to access this page.
            </p>
            <p className="text-sm text-gray-400">
              Required role: <span className="text-blue-400 font-semibold">{requiredRole}</span>
              <br />
              Your role: <span className="text-blue-400 font-semibold">{user.role}</span>
            </p>
            <button
              onClick={() => window.history.back()}
              className="mt-6 px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
            >
              Go Back
            </button>
          </div>
        </div>
      );
    }
  }

  // User is authenticated and has required role
  return <>{children}</>;
};

export default ProtectedRoute;
