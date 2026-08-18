import Alert from 'react-bootstrap/Alert';
import { Navigate, useLocation } from 'react-router-dom';

import GoogleSignInButton from '../components/GoogleSignInButton';
import { useAuth } from '../context/AuthContext';

export default function LoginPage() {
  const { isAuthenticated, isLoading, loginWithGoogle } = useAuth();
  const location = useLocation();
  const authError = (location.state as { authError?: string } | null)?.authError;

  if (!isLoading && isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="auth-backdrop flex-grow-1 d-flex align-items-center justify-content-center px-3 py-5">
      <div className="auth-card p-4 p-sm-5 text-center" style={{ width: '100%', maxWidth: 420 }}>
        <div className="empty-state-mark d-inline-flex align-items-center justify-content-center mb-4" style={{ width: 48, height: 48, fontSize: '1.3rem' }}>
          ✦
        </div>
        <h1 className="h3 fw-bold mb-2">Welcome back</h1>
        <p className="text-secondary mb-4">Sign in with Google to start chatting.</p>
        {authError && (
          <Alert variant="danger" className="mb-4 text-start">
            {authError}
          </Alert>
        )}
        <GoogleSignInButton onClick={loginWithGoogle} />
      </div>
    </div>
  );
}
