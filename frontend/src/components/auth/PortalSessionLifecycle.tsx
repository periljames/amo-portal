import React, { useCallback, useEffect, useRef, useState } from "react";

import {
  PORTAL_IDLE_TIMEOUT_MS,
  PORTAL_IDLE_WARNING_MS,
  endSession,
  extendSession,
  extendSessionIfNeeded,
  getLastUserSessionActivityAt,
  getToken,
  getTokenSecondsRemaining,
  onSessionEvent,
  recordUserSessionActivity,
  recoverSessionAfterUnauthorized,
} from "../../services/auth";

const ACTIVITY_WRITE_THROTTLE_MS = 5_000;

/**
 * Portal-wide session deadline owner.
 *
 * Browser timers are throttled in hidden tabs, so relative timeout callbacks
 * alone cannot safely enforce inactivity. Every focus/visibility/pageshow
 * transition re-evaluates persisted wall-clock deadlines before it accepts a
 * new interaction. Activity is shared across tabs, while API polling is never
 * considered proof that a person is present.
 */
const PortalSessionLifecycle: React.FC = () => {
  const warningTimerRef = useRef<number | null>(null);
  const logoutTimerRef = useRef<number | null>(null);
  const countdownTimerRef = useRef<number | null>(null);
  const lastObservedActivityRef = useRef<number>(0);
  const [warningDeadlineAt, setWarningDeadlineAt] = useState<number | null>(null);
  const [secondsRemaining, setSecondsRemaining] = useState(0);

  const clearTimers = useCallback(() => {
    if (warningTimerRef.current !== null) window.clearTimeout(warningTimerRef.current);
    if (logoutTimerRef.current !== null) window.clearTimeout(logoutTimerRef.current);
    if (countdownTimerRef.current !== null) window.clearInterval(countdownTimerRef.current);
    warningTimerRef.current = null;
    logoutTimerRef.current = null;
    countdownTimerRef.current = null;
  }, []);

  const showWarning = useCallback((deadlineAt: number) => {
    setWarningDeadlineAt(deadlineAt);
    setSecondsRemaining(Math.max(0, Math.ceil((deadlineAt - Date.now()) / 1000)));
    if (countdownTimerRef.current !== null) window.clearInterval(countdownTimerRef.current);
    countdownTimerRef.current = window.setInterval(() => {
      setSecondsRemaining(Math.max(0, Math.ceil((deadlineAt - Date.now()) / 1000)));
    }, 1_000);
  }, []);

  const evaluateAndSchedule = useCallback((now = Date.now()) => {
    clearTimers();

    if (!getToken()) {
      setWarningDeadlineAt(null);
      return;
    }

    let lastActivityAt = Math.max(
      lastObservedActivityRef.current,
      getLastUserSessionActivityAt() || 0,
    ) || null;
    if (!lastActivityAt) {
      lastActivityAt = now;
      recordUserSessionActivity("session-start", now);
    }
    lastObservedActivityRef.current = Math.max(lastObservedActivityRef.current, lastActivityAt);

    const deadlineAt = lastActivityAt + PORTAL_IDLE_TIMEOUT_MS;
    const warningAt = deadlineAt - PORTAL_IDLE_WARNING_MS;
    if (now >= deadlineAt) {
      setWarningDeadlineAt(null);
      endSession("idle");
      return;
    }

    // Access JWTs are short-lived; the HttpOnly refresh cookie may still be valid.
    // Never hard-logout here — recover (or leave recovery to the fetch bridge).
    // Immediate handleAuthFailure("token-expired") caused mid-session "secure
    // session expired" logouts while the user was still active within idle limits.
    // Successful recovery emits "authenticated", which re-runs evaluateAndSchedule.
    const tokenSecondsRemaining = getTokenSecondsRemaining();
    if (tokenSecondsRemaining !== null && tokenSecondsRemaining <= 0) {
      void recoverSessionAfterUnauthorized("lifecycle-access-expired").catch(() => undefined);
    }

    logoutTimerRef.current = window.setTimeout(() => {
      setWarningDeadlineAt(null);
      endSession("idle");
    }, Math.max(0, deadlineAt - now));

    if (now >= warningAt) {
      showWarning(deadlineAt);
      return;
    }

    setWarningDeadlineAt(null);
    warningTimerRef.current = window.setTimeout(() => showWarning(deadlineAt), warningAt - now);
  }, [clearTimers, showWarning]);

  useEffect(() => {
    // Defer past mount so the initial schedule does not setState synchronously in this effect.
    const bootTimer = window.setTimeout(() => evaluateAndSchedule(), 0);

    const acceptHumanActivity = (event: Event) => {
      if (!getToken()) return;
      if (event.target instanceof Element && event.target.closest("[data-portal-session-dialog]")) return;
      const now = Date.now();
      const lastActivityAt = Math.max(
        lastObservedActivityRef.current,
        getLastUserSessionActivityAt() || 0,
      );

      // A first event after a throttled/hidden interval must not revive an
      // already expired session. The user is signed out before any refresh.
      if (lastActivityAt && now - lastActivityAt >= PORTAL_IDLE_TIMEOUT_MS) {
        clearTimers();
        setWarningDeadlineAt(null);
        endSession("idle");
        return;
      }

      lastObservedActivityRef.current = now;
      if (!lastActivityAt || now - lastActivityAt >= ACTIVITY_WRITE_THROTTLE_MS) {
        recordUserSessionActivity(event.type, now);
      }
      setWarningDeadlineAt(null);
      evaluateAndSchedule(now);
      void extendSessionIfNeeded(`user:${event.type}`)?.catch(() => undefined);
    };

    const revalidateAfterSuspension = () => {
      if (document.visibilityState === "hidden") return;
      evaluateAndSchedule(Date.now());
    };

    const activityEvents = ["pointerdown", "keydown", "wheel", "touchstart"] as const;
    activityEvents.forEach((name) => window.addEventListener(name, acceptHumanActivity, { passive: true, capture: true }));
    window.addEventListener("focus", revalidateAfterSuspension, true);
    window.addEventListener("pageshow", revalidateAfterSuspension, true);
    document.addEventListener("visibilitychange", revalidateAfterSuspension, true);

    const stopSessionEvents = onSessionEvent((detail) => {
      if (detail.type === "authenticated") {
        const at = Date.now();
        // Silent JWT/cookie recovery must not reset the idle clock — only real
        // sign-in (or an explicit activity event) counts as human presence.
        const recoveryReason = String(detail.reason || "");
        const isSilentRecovery =
          recoveryReason.includes("expired") ||
          recoveryReason.includes("unauthorized") ||
          recoveryReason.includes("recover") ||
          recoveryReason.includes("lifecycle");
        if (!isSilentRecovery) {
          lastObservedActivityRef.current = at;
          recordUserSessionActivity("authenticated", at);
        }
        evaluateAndSchedule(at);
        return;
      }
      if (detail.type === "activity" && detail.at && detail.at > lastObservedActivityRef.current) {
        lastObservedActivityRef.current = detail.at;
        evaluateAndSchedule(Date.now());
        return;
      }
      if (detail.type === "expired" || detail.type === "idle-logout" || detail.type === "manual-logout") {
        clearTimers();
        setWarningDeadlineAt(null);
      }
    });

    return () => {
      window.clearTimeout(bootTimer);
      activityEvents.forEach((name) => window.removeEventListener(name, acceptHumanActivity, true));
      window.removeEventListener("focus", revalidateAfterSuspension, true);
      window.removeEventListener("pageshow", revalidateAfterSuspension, true);
      document.removeEventListener("visibilitychange", revalidateAfterSuspension, true);
      stopSessionEvents();
      clearTimers();
    };
  }, [clearTimers, evaluateAndSchedule]);

  if (warningDeadlineAt === null) return null;

  return (
    <div
      className="tenant-shell__session-overlay"
      data-portal-session-dialog
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="portal-idle-title"
      aria-describedby="portal-idle-description"
    >
      <div className="tenant-shell__session-card">
        <h2 id="portal-idle-title">Still working?</h2>
        <p id="portal-idle-description">
          For your security, this session will end in <strong>{secondsRemaining}s</strong>.
        </p>
        <div>
          <button type="button" className="btn btn-secondary" onClick={() => endSession("manual")}>Sign out</button>
          <button
            type="button"
            className="btn btn-primary"
            autoFocus
            onClick={() => {
              const at = Date.now();
              lastObservedActivityRef.current = at;
              recordUserSessionActivity("idle-warning", at);
              setWarningDeadlineAt(null);
              evaluateAndSchedule(at);
              void extendSession("idle-warning").catch(() => undefined);
            }}
          >
            Stay signed in
          </button>
        </div>
      </div>
    </div>
  );
};

export default PortalSessionLifecycle;
