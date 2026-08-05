import React from "react";
import { AlertTriangle, RefreshCcw } from "lucide-react";
import { reportPortalError } from "../../services/portalError";

type PortalErrorBoundaryState = {
  error: Error | null;
};

export default class PortalErrorBoundary extends React.Component<React.PropsWithChildren, PortalErrorBoundaryState> {
  state: PortalErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): PortalErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error): void {
    reportPortalError(error, {
      source: "runtime",
      title: "This page could not be displayed",
      fallbackMessage: "Reload the page and try again. Your saved server records are not affected.",
      actionLabel: "Reload page",
      action: () => window.location.reload(),
      dedupeKey: `route-boundary:${error.name}:${error.message}`,
    });
  }

  private reload = (): void => {
    window.location.reload();
  };

  render(): React.ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <main className="portal-fatal-error" role="alert" aria-live="assertive" aria-atomic="true">
        <section className="portal-fatal-error__card" tabIndex={-1} ref={(element) => element?.focus()}>
          <AlertTriangle size={28} aria-hidden="true" />
          <div>
            <h1>This page could not be displayed</h1>
            <p>{this.state.error.message || "An unexpected application error occurred."}</p>
            <p>Reload the page and repeat the action. Any records already saved to the server remain available.</p>
          </div>
          <button type="button" onClick={this.reload}><RefreshCcw size={16} /> Reload page</button>
        </section>
      </main>
    );
  }
}
