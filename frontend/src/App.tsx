import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import { ThemeProvider } from './contexts/ThemeContext';
import LoginPage from './pages/LoginPage';
import ViewerApp from './ViewerApp';
import ProtectedRoute from './components/ProtectedRoute';

/**
 * Main App Component with Routing
 *
 * Implements application-wide routing with authentication protection.
 * Follows ISO 27001 A.9.4.1 - Information access restriction
 *
 * Routes:
 * - /login: Public authentication page
 * - /app: Protected medical imaging viewer (requires authentication)
 * - /: Redirects to login or app based on auth state
 */
function App() {
  return (
    <Router>
      <ThemeProvider>
        <AuthProvider>
          <Routes>
            {/* Public Routes */}
            <Route path="/login" element={<LoginPage />} />

            {/* Protected Routes */}
            <Route
              path="/app"
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
        </AuthProvider>
      </ThemeProvider>
    </Router>
  );
}

export default App;
