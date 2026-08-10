import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div className="flex-grow-1 d-flex flex-column align-items-center justify-content-center text-center p-4">
      <h1 className="display-4 fw-bold">404</h1>
      <p className="text-secondary mb-4">This page doesn't exist.</p>
      <Link to="/" className="btn btn-primary">
        Back to home
      </Link>
    </div>
  );
}
