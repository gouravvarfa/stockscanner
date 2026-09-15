import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}
interface State {
  error: Error | null;
}

/**
 * Scoped to the Top-Bottom page only. Without this, any render-time error
 * inside the page (a chart library assertion, say) propagates to the root
 * and React unmounts the ENTIRE app — the user just sees a blank white
 * screen with no clue what broke. Now the failure stays contained to this
 * page and actually reports itself.
 */
export class TopBottomErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Top-Bottom page error:", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="page">
        <div className="card state-block">
          <div className="state-title">Top Bottom Backtesting hit an error</div>
          <div className="state-subtitle" style={{ marginBottom: 12 }}>
            The rest of the app is unaffected. Details below (also in the browser console).
          </div>
          <pre
            style={{
              textAlign: "left",
              whiteSpace: "pre-wrap",
              fontSize: 12,
              opacity: 0.85,
              maxHeight: 240,
              overflow: "auto",
            }}
          >
            {error.message}
            {error.stack ? `\n\n${error.stack}` : ""}
          </pre>
          <button type="button" onClick={() => this.setState({ error: null })}>
            Try again
          </button>
        </div>
      </div>
    );
  }
}
