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
    <>
      <Container className="flex-grow-1 d-flex flex-column justify-content-center text-center py-5">
        <h1 className="display-4 fw-bold mb-3">Chat with AI, powered by Gemini</h1>
        <p className="lead text-secondary mb-4">
          A clean, fast chat interface backed by a production-grade FastAPI + LangGraph backend.
        </p>
        <div>
          <Link to="/login" className="btn btn-primary btn-lg">
            Get started
          </Link>
        </div>
      </Container>

      <Container className="pb-5">
        <Row className="g-4">
          {FEATURES.map((feature) => (
            <Col key={feature.title} md={4}>
              <div className="h-100 p-4 border rounded-3">
                <h5>{feature.title}</h5>
                <p className="text-secondary mb-0">{feature.body}</p>
              </div>
            </Col>
          ))}
        </Row>
      </Container>
    </>
  );
}
