import React, { useEffect, useState } from "react";

import { onSessionEvent } from "../../services/auth";
import DepartmentLayoutImpl from "./DepartmentLayoutImpl";

type Props = {
  amoCode: string;
  activeDepartment: string;
  children: React.ReactNode;
  showPollingErrorBanner?: boolean;
};

/**
 * Rebuild the portal shell after the authenticated access context changes.
 *
 * AccessRealtimeBridge refreshes /auth/me first, then emits the existing
 * authenticated session event. Remounting the shell at that point guarantees
 * navigation and module visibility are recalculated from the refreshed cached
 * user instead of waiting for an unrelated render or a new login.
 */
export default function AccessAwareDepartmentLayout(props: Props) {
  const [accessRevision, setAccessRevision] = useState(0);

  useEffect(() => onSessionEvent((detail) => {
    if (detail.type !== "authenticated" || detail.reason !== "access-context-changed") return;
    setAccessRevision((value) => value + 1);
  }), []);

  return <DepartmentLayoutImpl key={accessRevision} {...props} />;
}
