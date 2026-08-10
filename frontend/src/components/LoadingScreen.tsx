import Spinner from 'react-bootstrap/Spinner';

export default function LoadingScreen({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="d-flex flex-column align-items-center justify-content-center vh-100 gap-3 text-secondary">
      <Spinner animation="border" role="status">
        <span className="visually-hidden">{label}</span>
      </Spinner>
      <div>{label}</div>
    </div>
  );
}
