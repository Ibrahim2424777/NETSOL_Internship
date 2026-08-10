import Alert from 'react-bootstrap/Alert';
import Container from 'react-bootstrap/Container';
import { Navigate, useLocation } from 'react-router-dom';

import GoogleSignInButton from '../components/GoogleSignInButton';
import { useAuth } from '../context/AuthContext';

export default function LoginPage() {
  const { isAuthenticated, isLoading, loginWithGoogle } = useAuth();
  const location = useLocation();
  const authError = (location.state as { authError?: string } | null)?.authError;

  if (!isLoading && isAuthenticated) {
    return <Navigate to="/chat" replace />;
  }

  return (
    <Container className="flex-grow-1 d-flex flex-column align-items-center justify-content-center text-center py-5">
      <h1 className="h3 fw-bold mb-2">Welcome back</h1>
      <p className="text-secondary mb-4">Sign in with Google to start chatting.</p>
      {authError && (
        <Alert variant="danger" className="mb-4" style={{ maxWidth: 420 }}>
          {authError}
        </Alert>
      )}
      <GoogleSignInButton onClick={loginWithGoogle} />
    </Container>
  );
}
