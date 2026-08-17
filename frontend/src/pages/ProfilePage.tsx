import Container from 'react-bootstrap/Container';

import { useAuth } from '../context/AuthContext';

// Read-only for now: the backend doesn't have an Update Profile endpoint
// yet (only GET /auth/me), so there's nothing to wire an edit form up to.
export default function ProfilePage() {
  const { user } = useAuth();

  if (!user) return null;

  const memberSince = new Date(user.created_at).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

  return (
    <Container className="py-5" style={{ maxWidth: 480 }}>
      <div className="auth-card p-4 text-center">
        {user.profile_picture ? (
          <img
            src={user.profile_picture}
            alt=""
            width={88}
            height={88}
            className="rounded-circle mb-3"
            referrerPolicy="no-referrer"
          />
        ) : (
          <div
            className="rounded-circle text-on-accent d-inline-flex align-items-center justify-content-center mb-3"
            style={{ width: 88, height: 88, fontSize: '1.8rem', background: 'var(--app-accent-gradient)' }}
          >
            {user.name.charAt(0).toUpperCase()}
          </div>
        )}
        <h4 className="mb-1">{user.name}</h4>
        <p className="text-secondary mb-3">{user.email}</p>
        <p className="text-secondary small mb-0">Member since {memberSince}</p>
      </div>
    </Container>
  );
}
