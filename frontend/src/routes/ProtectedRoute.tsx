import { Navigate, Outlet, useLocation } from 'react-router-dom';

import LoadingScreen from '../components/LoadingScreen';
import { useAuth } from '../context/AuthContext';

// Wraps every route that requires a logged-in user (Chat, Profile). While
// the app is still attempting its one silent-refresh-on-load call (see
// AuthContext), we don't know yet whether the user is authenticated, so we
// show a loading screen rather than bouncing them to /login and then
// immediately back.
export default function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <LoadingScreen label="Checking your session…" />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <Outlet />;
}
