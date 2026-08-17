import LoadingScreen from '../components/LoadingScreen';
import MarketingLanding from '../components/landing/MarketingLanding';
import PersonalizedLanding from '../components/landing/PersonalizedLanding';
import { useAuth } from '../context/AuthContext';

// `/` adapts to auth state (Phase 15 section 3): a polished marketing page
// for a logged-out visitor, or a personalized dashboard (greeting, recent
// conversations, sidebar) for a returning signed-in user - see
// PublicLayout.tsx for how the surrounding chrome avoids double-rendering a
// header in the personalized case.
export default function LandingPage() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return <LoadingScreen />;
  }

  return isAuthenticated ? <PersonalizedLanding /> : <MarketingLanding />;
}
