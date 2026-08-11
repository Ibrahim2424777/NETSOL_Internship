import Col from 'react-bootstrap/Col';
import Container from 'react-bootstrap/Container';
import Row from 'react-bootstrap/Row';
import { Link } from 'react-router-dom';

const FEATURES = [
  {
    title: 'Powered by Gemini',
    body: 'Every conversation runs through a LangGraph workflow calling Google’s Gemini model.',
  },
  {
    title: 'Real-time streaming',
    body: 'Responses stream in as they’re generated, instead of waiting for the full reply.',
  },
  {
    title: 'Secure by design',
    body: 'Sign in with Google. Your session is protected with short-lived tokens the frontend never stores.',
  },
];

export default function LandingPage() {
  return (
    <div className="auth-backdrop flex-grow-1 d-flex flex-column">
      <Container className="flex-grow-1 d-flex flex-column justify-content-center text-center py-5">
        <div className="empty-state-mark d-inline-flex align-items-center justify-content-center mb-4 mx-auto" style={{ width: 48, height: 48, fontSize: '1.3rem' }}>
          ✦
        </div>
        <h1 className="display-5 fw-bold mb-3">
          Chat with AI, <span className="gradient-text">powered by Gemini</span>
        </h1>
        <p className="lead text-secondary mb-4 mx-auto" style={{ maxWidth: 560 }}>
          A clean, fast chat interface backed by a production-grade FastAPI + LangGraph backend.
        </p>
        <div>
          <Link to="/login" className="btn btn-gradient btn-lg px-4">
            Get started
          </Link>
        </div>
      </Container>

      <Container className="pb-5">
        <Row className="g-4">
          {FEATURES.map((feature) => (
            <Col key={feature.title} md={4}>
              <div className="feature-card h-100 p-4">
                <h5 className="mb-2">{feature.title}</h5>
                <p className="text-secondary mb-0 small">{feature.body}</p>
              </div>
            </Col>
          ))}
        </Row>
      </Container>
    </div>
  );
}
