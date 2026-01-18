import { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { SessionManager } from './components/SessionManager';
import { SkipLink } from './components/SkipLink';
import LoginPage from './pages/LoginPage';
import PatientsPage from './pages/PatientsPage';
import PatientDetailPage from './pages/PatientDetailPage';
import DocumentsPage from './pages/DocumentsPage';
import ViewerApp from './ViewerApp';
import ProtectedRoute from './components/ProtectedRoute';
import { initializeFocusVisible } from './utils/accessibility';

/**
 * Main App Component with Routing
 *
 * Implements application-wide routing with authentication protection.
 * Follows ISO 27001 A.9.4.1 - Information access restriction
 *
 * Routes:
 * - /login: Public authentication page
 * - /app: Protected main dashboard / viewer (requires authentication)
 * - /app/patients: Patient management page
 * - /app/patients/:patientId: Patient detail page
 * - /app/documents: Document management page
 * - /app/viewer: Medical imaging viewer
 * - /: Redirects to login or app based on auth state
 */
function App() {
  // Initialize keyboard focus visibility detection for WCAG 2.4.7
  useEffect(() => {
    initializeFocusVisible();
  }, []);

  return (
    <Router>
      <ThemeProvider>
        <AuthProvider>
          {/* WCAG 2.4.1: Skip navigation link for keyboard users */}
          <SkipLink mainContentId="main-content" />

          {/* HIPAA-compliant session timeout management (15 minutes) */}
          <SessionManager timeoutMinutes={15} warningMinutes={2}>
            <Routes>
              {/* Public Routes */}
              <Route path="/login" element={<LoginPage />} />

              {/* Protected Routes */}
              <Route
                path="/app"
                element={
                  <ProtectedRoute>
                    <PatientsPage />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/app/patients"
                element={
                  <ProtectedRoute>
                    <PatientsPage />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/app/patients/:patientId"
                element={
                  <ProtectedRoute>
                    <PatientDetailPage />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/app/documents"
                element={
                  <ProtectedRoute>
                    <DocumentsPage />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/app/viewer"
                element={
                  <ProtectedRoute>
                    <ViewerApp />
                  </ProtectedRoute>
                }
              />

              {/* Default Route - Redirect to app (will redirect to login if not authenticated) */}
              <Route path="/" element={<Navigate to="/app" replace />} />

              {/* Catch all - redirect to root */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </SessionManager>
        </AuthProvider>
      </ThemeProvider>
    </Router>
  );
}

export default App;
