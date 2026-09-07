import React from "react";

import { reportPortalError } from "../../services/portalError";

type PortalAuxiliaryBoundaryProps = React.PropsWithChildren<{
  surface: string;
}>;

type PortalAuxiliaryBoundaryState = {
  failed: boolean;
};

/**
 * Isolates non-essential root controls from the primary portal tree. A failure
 * in messaging, connectivity or offline sync must never unmount the login or
 * active workspace.
 */
export default class PortalAuxiliaryBoundary extends React.Component<
  PortalAuxiliaryBoundaryProps,
  PortalAuxiliaryBoundaryState
> {
  state: PortalAuxiliaryBoundaryState = { failed: false };

  static getDerivedStateFromError(): PortalAuxiliaryBoundaryState {
    return { failed: true };
  }

  componentDidCatch(error: Error): void {
    // Defer until parent passive effects have installed the global alert
    // bridge; otherwise an initial-render failure can emit before it listens.
    window.setTimeout(() => {
      reportPortalError(error, {
        source: "runtime",
        title: `${this.props.surface} are temporarily unavailable`,
        fallbackMessage: "The main portal remains available. Reload the page to retry these controls.",
        actionLabel: "Reload page",
        action: () => window.location.reload(),
        dedupeKey: `auxiliary-boundary:${this.props.surface}:${error.name}:${error.message}`,
      });
    }, 0);
  }

  render(): React.ReactNode {
    return this.state.failed ? null : this.props.children;
  }
}
