import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

// Without this, an unexpected error thrown during render anywhere in the
// tree (a malformed API response, a third-party component's own bug) takes
// the entire app down to a blank white screen with nothing but a console
// error - not something to explain to a non-technical user. This is a class
// component because React has no hook equivalent for componentDidCatch /
// getDerivedStateFromError; it's one of the few remaining cases where one
// is required.
export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error('Unhandled render error caught by ErrorBoundary:', error, errorInfo);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="d-flex flex-column align-items-center justify-content-center vh-100 gap-3 text-center px-3">
          <h1 className="h4">Something went wrong.</h1>
          <p className="text-secondary mb-0">
            Please refresh the page. If this keeps happening, try signing out and back in.
          </p>
          <button type="button" className="btn btn-primary" onClick={() => window.location.assign('/')}>
            Back to home
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
