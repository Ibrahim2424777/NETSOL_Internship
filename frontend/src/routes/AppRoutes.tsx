import { Route, Routes } from 'react-router-dom';

import AppLayout from '../layouts/AppLayout';
import PublicLayout from '../layouts/PublicLayout';
import AuthCallbackPage from '../pages/AuthCallbackPage';
import ChatPage from '../pages/ChatPage';
import LandingPage from '../pages/LandingPage';
import LoginPage from '../pages/LoginPage';
import NotFoundPage from '../pages/NotFoundPage';
import ProfilePage from '../pages/ProfilePage';
import ProtectedRoute from './ProtectedRoute';

export default function AppRoutes() {
  return (
    <Routes>
      {/* Public pages share a light header (see PublicLayout). The OAuth
          callback also lives here - it's reachable while logged out. */}
      <Route element={<PublicLayout />}>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>

      {/* Everything below requires a logged-in user (ProtectedRoute), and
          shares the authenticated navbar (AppLayout). */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:chatId" element={<ChatPage />} />
          <Route path="/profile" element={<ProfilePage />} />
        </Route>
      </Route>
    </Routes>
  );
}
