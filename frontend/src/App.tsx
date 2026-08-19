import { useEffect, lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { MotionConfig } from 'framer-motion';
import { AuthProvider } from './contexts/AuthContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { SessionManager } from './components/SessionManager';
import { SkipLink } from './components/SkipLink';
import LoginPage from './pages/LoginPage';   // eager: first paint, keep the login bundle tiny
import ProtectedRoute from './components/ProtectedRoute';
import { initializeFocusVisible } from './utils/accessibility';
import KeyboardShortcutsModal from './components/KeyboardShortcutsModal';

// Route-level code splitting: the authenticated app — and especially the ~316 kB-gzip
// niivue engine inside ViewerApp — loads only when its route is entered, so the login /
// first paint no longer ships the whole 3D/report machinery.
// The import thunks are named so they can ALSO be prefetched during idle (below): the
// lazy split keeps first paint light, and the idle prefetch removes the full-screen
// Suspense spinner on the FIRST navigation into each route (self-inflicted by the split).
const loadPatients = () => import('./pages/PatientsPage');
const loadPatientDetail = () => import('./pages/PatientDetailPage');
const loadDocuments = () => import('./pages/DocumentsPage');
const loadViewer = () => import('./ViewerApp');
const loadPACS = () => import('./pages/PACSBrowserPage');
const loadProfile = () => import('./pages/ProfilePage');

const PatientsPage = lazy(loadPatients);
const PatientDetailPage = lazy(loadPatientDetail);
const DocumentsPage = lazy(loadDocuments);
const ViewerApp = lazy(loadViewer);
const PACSBrowserPage = lazy(loadPACS);
const ProfilePage = lazy(loadProfile);

/** Minimal route-transition fallback, dark-theme matched. */
function RouteFallback() {
  return (
    <div
      role="status"
      aria-live="polite"
      style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: '#08090C' }}
    >
      <div
        aria-hidden
        className="animate-spin"
        style={{
          width: 28, height: 28, borderRadius: '9999px',
          border: '2px solid #232833', borderTopColor: '#35B4C4',
        }}
      />
      <span style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' }}>
        Loading…
      </span>
    </div>
  );
}

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

  // Warm the most-visited route chunks during browser idle AFTER first paint, so the
  // first navigation into them doesn't flash the full-screen Suspense fallback. Dynamic
  // imports are cached + idempotent and this is idle-scheduled, so it never competes with
  // login/first paint; a real navigation that beats the prefetch just resolves the same
  // promise. Ordered by likelihood: patient list → detail → viewer.
  useEffect(() => {
    const warm = () => { loadPatients(); loadPatientDetail(); loadViewer(); };
    const w = window as Window & {
      requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number;
      cancelIdleCallback?: (id: number) => void;
    };
    let idleId: number | undefined;
    let timerId: ReturnType<typeof setTimeout> | undefined;
    if (typeof w.requestIdleCallback === 'function') {
      idleId = w.requestIdleCallback(warm, { timeout: 4000 });
    } else {
      timerId = setTimeout(warm, 2000);
    }
    return () => {
      if (idleId !== undefined && typeof w.cancelIdleCallback === 'function') w.cancelIdleCallback(idleId);
      if (timerId !== undefined) clearTimeout(timerId);
    };
  }, []);

  return (
    // WCAG 2.3.3 + vestibular safety: honor the OS "reduce motion" setting across every
    // framer-motion animation in the app (entrance transitions, spinners, etc.).
    <MotionConfig reducedMotion="user">
    <Router>
      <ThemeProvider>
        <AuthProvider>
          {/* WCAG 2.4.1: Skip navigation link for keyboard users */}
          <SkipLink mainContentId="main-content" />
          <KeyboardShortcutsModal />

          {/* HIPAA-compliant session timeout management (15 minutes) */}
          <SessionManager timeoutMinutes={15} warningMinutes={2}>
            <Suspense fallback={<RouteFallback />}>
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
                path="/app/pacs"
                element={
                  <ProtectedRoute>
                    <PACSBrowserPage />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/app/profile"
                element={
                  <ProtectedRoute>
                    <ProfilePage />
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
            </Suspense>
          </SessionManager>
        </AuthProvider>
      </ThemeProvider>
    </Router>
    </MotionConfig>
  );
}

export default App;
