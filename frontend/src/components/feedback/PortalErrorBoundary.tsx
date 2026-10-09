import React from "react";
import { AlertTriangle, RefreshCcw } from "lucide-react";
import "./portalErrorBoundary.css";

type PortalErrorBoundaryState = {
  error: Error | null;
};

type Props = React.PropsWithChildren<{
  inline?: boolean;
  title?: string;
  exitHref?: string;
  exitLabel?: string;
}>;

export default class PortalErrorBoundary extends React.Component<Props, PortalErrorBoundaryState> {
  state: PortalErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): PortalErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    // Retain diagnostics for support without showing JavaScript internals or a
    // second global error overlay over the recovery controls below.
    console.error("[PortalErrorBoundary]", error, info.componentStack);
  }

  private reload = (): void => {
    window.location.reload();
  };

  render(): React.ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <div className={`portal-fatal-error${this.props.inline ? " portal-fatal-error--inline" : ""}`} role="alert" aria-live="assertive" aria-atomic="true">
        <section className="portal-fatal-error__card" tabIndex={-1} ref={(element) => element?.focus()}>
          <AlertTriangle size={28} aria-hidden="true" />
          <div>
            <h2>{this.props.title || "This page could not be displayed"}</h2>
            <p>An application problem prevented this {this.props.inline ? "section" : "page"} from loading. Saved records remain available.</p>
            <p>{this.props.inline ? "Try this section again. Other sections remain available." : "Reload the page to load the current saved records. Review any unsaved changes before repeating the action."}</p>
          </div>
          <div className="portal-fatal-error__actions">
            <button type="button" onClick={this.props.inline ? () => this.setState({ error: null }) : this.reload}><RefreshCcw size={16} /> {this.props.inline ? "Try again" : "Reload page"}</button>
            {this.props.exitHref ? <a href={this.props.exitHref}>{this.props.exitLabel || "Back to audit"}</a> : null}
          </div>
        </section>
      </div>
    );
  }
}
