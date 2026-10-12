/** Browser-only, authenticated QMS offline synchronization.
 *
 * The service worker cannot access the session credentials or encryption keys.
 * Once a portal tab is reopened/authenticated, replay the encrypted outbox
 * first, then evidence. Never report "synced" for device-only changes.
 */
import { getToken, getTokenSecondsRemaining } from "./auth";
import { currentOfflineScope, onOfflineStateChanged, replayOfflineMutations } from "./offlinePersistence";
import { onOfflineAuditEvidenceChanged, listPendingAuditEvidenceGroups, synchronizeOfflineAuditEvidence } from "./qmsOfflineAuditEvidence";
import { getPortalConnectivity, isPortalReady, onPortalConnectivityChange } from "./portalConnectivity";

const PERIODIC_RETRY_MS = 30_000;
let inFlight: Promise<void> | null = null;
let scheduled: number | null = null;
let lastAttemptAt = 0;

function canSynchronize(): boolean {
  const remaining = getTokenSecondsRemaining();
  return isPortalReady() && Boolean(getToken()) && (remaining === null || remaining > 0)
    && (typeof navigator === "undefined" || navigator.onLine !== false);
}

async function syncAuditQueues(): Promise<void> {
  if (!canSynchronize()) return;
  const scope = currentOfflineScope();
  await replayOfflineMutations();
  if (!canSynchronize() || scope !== currentOfflineScope()) return;
  const groups = await listPendingAuditEvidenceGroups();
  for (const group of groups) {
    if (!canSynchronize() || scope !== currentOfflineScope()) break;
    if (group.count <= group.conflicts) continue;
    try {
      // Recheck the scoped queue before uploading. In-progress work in another
      // tab is protected by the evidence sync Web Lock.
      const pending = await listPendingAuditEvidenceGroups();
      if (pending.some((item) => item.amoCode === group.amoCode && item.auditId === group.auditId
        && item.count > item.conflicts)) {
        await synchronizeOfflineAuditEvidence(group.amoCode, group.auditId);
      }
    } catch {
      // Device-encrypted files remain queued and will retry in a later pass.
    }
  }
}

/** Manually invoked full replay: checklist commands first, then encrypted evidence. */
export function synchronizeAuditOfflineNow(): Promise<void> {
  if (!canSynchronize()) return Promise.resolve();
  if (inFlight) return inFlight;
  lastAttemptAt = Date.now();
  inFlight = syncAuditQueues().finally(() => { inFlight = null; });
  return inFlight;
}

/** Visible sessions sync on recovery, focus, tab reopen, or timed retry. */
export function requestAuditOfflineSync(force = false): void {
  if (typeof window === "undefined" || !canSynchronize()) return;
  if (inFlight) return;
  const now = Date.now();
  if (!force && now - lastAttemptAt < 5_000) return;
  if (scheduled !== null) window.clearTimeout(scheduled);
  scheduled = window.setTimeout(() => {
    scheduled = null;
    if (!canSynchronize() || inFlight) return;
    void synchronizeAuditOfflineNow().catch(() => undefined);
  }, force ? 0 : 300);
}

export function startAuditOfflineSync(): () => void {
  if (typeof window === "undefined") return () => undefined;
  const recheck = () => requestAuditOfflineSync();
  const ready = onPortalConnectivityChange((connection) => {
    if (connection.state === "ONLINE") requestAuditOfflineSync(true);
  });
  const device = onOfflineStateChanged(recheck);
  const evidence = onOfflineAuditEvidenceChanged(recheck);
  const visible = () => { if (document.visibilityState === "visible") requestAuditOfflineSync(true); };
  const online = () => requestAuditOfflineSync(true);
  const period = window.setInterval(() => {
    if (document.visibilityState === "visible" && getPortalConnectivity().state === "ONLINE") {
      requestAuditOfflineSync(true);
    }
  }, PERIODIC_RETRY_MS);
  document.addEventListener("visibilitychange", visible);
  window.addEventListener("focus", online);
  window.addEventListener("online", online);
  requestAuditOfflineSync();
  return () => {
    ready();
    device();
    evidence();
    window.clearInterval(period);
    if (scheduled !== null) window.clearTimeout(scheduled);
    document.removeEventListener("visibilitychange", visible);
    window.removeEventListener("focus", online);
    window.removeEventListener("online", online);
  };
}
