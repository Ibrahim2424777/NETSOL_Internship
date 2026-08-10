import Card from 'react-bootstrap/Card';
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
      <Card>
        <Card.Body className="text-center p-4">
          {user.profile_picture ? (
            <img
              src={user.profile_picture}
              alt=""
              width={96}
              height={96}
              className="rounded-circle mb-3"
              referrerPolicy="no-referrer"
            />
          ) : (
            <div
              className="rounded-circle bg-secondary text-white d-inline-flex align-items-center justify-content-center mb-3"
              style={{ width: 96, height: 96, fontSize: '2rem' }}
            >
              {user.name.charAt(0).toUpperCase()}
            </div>
          )}
          <h4 className="mb-1">{user.name}</h4>
          <p className="text-secondary mb-3">{user.email}</p>
          <p className="text-secondary small mb-0">Member since {memberSince}</p>
        </Card.Body>
      </Card>
    </Container>
  );
}
