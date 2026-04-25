import { Component, type ErrorInfo, type ReactNode } from "react";

type ErrorBoundaryProps = {
  children: ReactNode;
};

type ErrorBoundaryState = {
  error: Error | null;
};

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error("Top-level render error captured by ErrorBoundary.", error, errorInfo);
  }

  private handleReload = (): void => {
    window.location.reload();
  };

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="app-shell" data-route-theme="admin" role="alert">
          <section className="error-boundary-card">
            <p className="eyebrow">Something went wrong</p>
            <h1>The page hit an unexpected error</h1>
            <p>
              The interface stopped rendering before it could finish loading. The
              underlying APIs may still be reachable. Try a reload, and if the
              issue persists, capture the browser console output for triage.
            </p>
            <pre className="error-boundary-detail">{this.state.error.message}</pre>
            <button
              type="button"
              className="primary-action"
              onClick={this.handleReload}
            >
              Reload page
            </button>
          </section>
        </div>
      );
    }

    return this.props.children;
  }
}
