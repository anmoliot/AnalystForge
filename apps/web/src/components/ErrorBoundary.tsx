import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Unhandled UI error", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-dvh items-center justify-center bg-canvas p-6">
          <div className="panel w-full max-w-md p-6">
            <p className="panel-title">Application error</p>
            <h1 className="mt-2 text-lg font-semibold">Something broke in this view</h1>
            <p className="mt-2 text-sm text-muted">
              The rest of the workspace is unaffected. Reload to continue; if the problem persists,
              quote the message below to your administrator.
            </p>
            <pre className="mt-4 max-h-32 overflow-auto rounded border border-line bg-elevated p-3 font-mono text-2xs text-negative">
              {this.state.error.message}
            </pre>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="mt-4 inline-flex h-8 items-center rounded bg-accent px-3 text-sm font-medium text-accent-ink"
            >
              Reload workspace
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
