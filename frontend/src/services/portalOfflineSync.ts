/** Browser-only, authenticated portal offline synchronization.
 *
 * The service worker cannot access the session credentials or encryption keys.
 * Once a portal tab is reopened/authenticated, replay the encrypted outbox
 * first, then evidence. Never report "synced" for device-only changes.
 */
import { getToken, getTokenSecondsRemaining } from "./auth";
import { currentOfflineScope, listOfflineMutations, onOfflineStateChanged, replayOfflineMutations } from "./offlinePersistence";
import { onOfflineAuditEvidenceChanged, listPendingAuditEvidenceGroups, synchronizeOfflineAuditEvidence } from "./qmsOfflineAuditEvidence";
import { isPortalReady, onPortalConnectivityChange } from "./portalConnectivity";

const PERIODIC_RETRY_MS = 30_000;
let inFlight: Promise<void> | null = null;
let scheduled: number | null = null;
let resyncRequested = false;
let running = false;

function canSynchronize(): boolean {
  const remaining = getTokenSecondsRemaining();
  return isPortalReady() && Boolean(getToken()) && (remaining === null || remaining > 0)
    && (typeof navigator === "undefined" || navigator.onLine !== false);
}

async function syncPortalQueues(): Promise<void> {
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
export function synchronizePortalOfflineNow(): Promise<void> {
  if (!canSynchronize()) return Promise.resolve();
  if (inFlight) return inFlight;
  resyncRequested = false;
  inFlight = syncPortalQueues().finally(async () => {
    if (!running || !canSynchronize()) { inFlight = null; return; }
    // Changes arriving during a replay must not wait for the 30-second sweep.
    // Backoff uses each command's due time instead of the sweep interval.
    const entries = await listOfflineMutations().catch(() => []);
    inFlight = null;
    if (!running || !canSynchronize()) return;
    const future = entries.filter((entry) => entry.status === "queued" && (entry.nextAttemptAt || 0) > Date.now())
      .map((entry) => entry.nextAttemptAt! - Date.now());
    const delay = resyncRequested ? 300 : Math.min(PERIODIC_RETRY_MS, ...future);
    if (scheduled !== null) window.clearTimeout(scheduled);
    scheduled = window.setTimeout(() => {
      scheduled = null;
      requestPortalOfflineSync(true);
    }, Math.max(300, delay));
  });
  return inFlight;
}

/** Authenticated sessions sync on recovery, focus, tab reopen, or timed retry. */
export function requestPortalOfflineSync(force = false): void {
  if (typeof window === "undefined" || !canSynchronize()) return;
  if (inFlight) { resyncRequested = true; return; }
  if (scheduled !== null) window.clearTimeout(scheduled);
  scheduled = window.setTimeout(() => {
    scheduled = null;
    if (!canSynchronize() || inFlight) return;
    void synchronizePortalOfflineNow().catch(() => undefined);
  }, force ? 0 : 300);
}

export function startPortalOfflineSync(): () => void {
  if (typeof window === "undefined" || running) return () => undefined;
  running = true;
  const recheck = () => requestPortalOfflineSync();
  const ready = onPortalConnectivityChange((connection) => {
    if (connection.state === "ONLINE") requestPortalOfflineSync(true);
  });
  const device = onOfflineStateChanged(recheck);
  const evidence = onOfflineAuditEvidenceChanged(recheck);
  const visible = () => { if (document.visibilityState === "visible") requestPortalOfflineSync(true); };
  const online = () => requestPortalOfflineSync(true);
  document.addEventListener("visibilitychange", visible);
  window.addEventListener("focus", online);
  window.addEventListener("online", online);
  requestPortalOfflineSync();
  return () => {
    running = false;
    ready();
    device();
    evidence();
    if (scheduled !== null) window.clearTimeout(scheduled);
    document.removeEventListener("visibilitychange", visible);
    window.removeEventListener("focus", online);
    window.removeEventListener("online", online);
  };
}
