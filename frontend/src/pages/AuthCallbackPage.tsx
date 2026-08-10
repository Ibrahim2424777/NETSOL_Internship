import { useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import LoadingScreen from '../components/LoadingScreen';
import { useAuth } from '../context/AuthContext';

// Google redirects the browser here with ?code=... after the user approves
// sign-in (see authApi.ts:buildGoogleAuthUrl - redirect_uri points at this
// route). This page's only job is handing that code to the backend and
// moving on.
//
// exchangeStarted guards against React 18 StrictMode's dev-mode behavior of
// running effects twice: Google's authorization code is single-use, so a
// second exchange attempt with the same code would be rejected by Google,
// surfacing a spurious error on a login that actually succeeded.
export default function AuthCallbackPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { completeGoogleLogin } = useAuth();
  const exchangeStarted = useRef(false);

  useEffect(() => {
    if (exchangeStarted.current) return;
    exchangeStarted.current = true;

    const code = searchParams.get('code');
    const oauthError = searchParams.get('error');

    if (oauthError) {
      navigate('/login', { replace: true, state: { authError: 'Google sign-in was cancelled.' } });
      return;
    }
    if (!code) {
      navigate('/login', { replace: true, state: { authError: 'Missing authorization code from Google.' } });
      return;
    }

    completeGoogleLogin(code)
      .then(() => navigate('/chat', { replace: true }))
      .catch(() =>
        navigate('/login', { replace: true, state: { authError: 'Sign-in failed. Please try again.' } }),
      );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <LoadingScreen label="Signing you in…" />;
}
