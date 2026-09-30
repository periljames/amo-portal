import { apiRequest, qmsPath } from "./apiClient";
import {
  currentOfflineScope,
  decryptDeviceValue,
  encryptDeviceValue,
  type EncryptedDeviceValue,
} from "./offlinePersistence";

export type AuditOfflinePack = {
  schema: "QMS_AUDIT_OFFLINE_PACK_V1";
  generated_at: string;
  audit_id: string;
  work_package: {
    id: string;
    audit_id: string;
    preparation_revision_id: string;
    revision_no: number;
    package_snapshot: {
      schema: "QMS_AUDIT_WORK_PACKAGE_V1";
      audit: Record<string, unknown>;
      preparation: Record<string, unknown>;
      checklist_snapshot: Array<Record<string, unknown>>;
      document_request_definitions: Array<Record<string, unknown>>;
      source_references: Array<Record<string, unknown>>;
      prior_audits: Array<Record<string, unknown>>;
      prior_findings: Array<Record<string, unknown>>;
      prior_cars: Array<Record<string, unknown>>;
      meetings: Array<Record<string, unknown>>;
    };
    content_sha256: string;
    offline_expires_at?: string | null;
    supersedes_work_package_id?: string | null;
    issued_by_user_id?: string | null;
    issued_at: string;
    created_at: string;
  };
  execution: Array<{
    checklist_item_id: string;
    canonical_response_status: string;
    response_value?: string | null;
    auditor_notes?: string | null;
    evidence_references: Array<Record<string, unknown> | string>;
    entity_version: number;
    updated_at?: string | null;
  }>;
  findings: Array<Record<string, unknown>>;
  evidence: Array<{
    id: string;
    checklist_item_id?: string | null;
    finding_id?: string | null;
    filename: string;
    content_type?: string | null;
    size_bytes: number;
    sha256: string;
    description?: string | null;
    created_at?: string | null;
  }>;
  sync_contract: {
    server_authoritative: boolean;
    conflict_strategy: string;
    idempotency: string;
    binary_evidence_state: string;
  };
};

export type AuditOfflinePackStatus = {
  ready: boolean;
  storedAt: number | null;
  verifiedAt: number | null;
  workPackageSha256: string | null;
  checklistItems: number;
  evidenceRecords: number;
  expiresAt: number | null;
};

type StoredAuditOfflinePack = {
  key: string;
  scope: string;
  amoCode: string;
  auditId: string;
  workPackageId: string;
  workPackageSha256: string;
  storedAt: number;
  verifiedAt: number;
  expiresAt: number | null;
  encrypted: EncryptedDeviceValue;
};

const DB_NAME = "amo-qms-offline-packs";
const DB_VERSION = 1;
const STORE = "packs";

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Offline audit-pack storage failed."));
  });
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error || new Error("Offline audit-pack transaction failed."));
    transaction.onabort = () => reject(transaction.error || new Error("Offline audit-pack transaction aborted."));
  });
}

async function openDb(): Promise<IDBDatabase> {
  if (typeof indexedDB === "undefined") throw new Error("This browser does not provide durable offline storage.");
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE)) {
        const store = request.result.createObjectStore(STORE, { keyPath: "key" });
        store.createIndex("scope", "scope", { unique: false });
        store.createIndex("audit", ["scope", "auditId"], { unique: true });
        store.createIndex("storedAt", "storedAt", { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Unable to open offline audit-pack storage."));
  });
}

function packKey(scope: string, auditId: string): string {
  return `${scope}:${auditId}`;
}

export async function fetchAuditOfflinePack(
  amoCode: string,
  auditId: string,
  signal?: AbortSignal,
): Promise<AuditOfflinePack> {
  return apiRequest<AuditOfflinePack>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/offline-pack`),
    { timeoutMs: 30_000, cacheTtlMs: 0, signal },
  );
}

export async function prepareAuditOfflinePack(
  amoCode: string,
  auditId: string,
): Promise<{ pack: AuditOfflinePack; status: AuditOfflinePackStatus }> {
  const pack = await fetchAuditOfflinePack(amoCode, auditId);
  const scope = currentOfflineScope();
  if (scope.startsWith("anonymous:")) throw new Error("Sign in before storing a controlled audit package on this device.");
  const encrypted = await encryptDeviceValue(pack);
  if (!encrypted) throw new Error("Secure device encryption is unavailable; the audit package was not stored.");

  const now = Date.now();
  const parsedExpiry = pack.work_package.offline_expires_at
    ? Date.parse(pack.work_package.offline_expires_at)
    : Number.NaN;
  const expiresAt = Number.isFinite(parsedExpiry) ? parsedExpiry : null;
  const row: StoredAuditOfflinePack = {
    key: packKey(scope, auditId),
    scope,
    amoCode,
    auditId,
    workPackageId: pack.work_package.id,
    workPackageSha256: pack.work_package.content_sha256,
    storedAt: now,
    verifiedAt: now,
    expiresAt,
    encrypted,
  };
  const db = await openDb();
  try {
    const transaction = db.transaction(STORE, "readwrite");
    transaction.objectStore(STORE).put(row);
    await transactionDone(transaction);
  } finally {
    db.close();
  }
  return {
    pack,
    status: {
      ready: true,
      storedAt: row.storedAt,
      verifiedAt: row.verifiedAt,
      workPackageSha256: row.workPackageSha256,
      checklistItems: pack.work_package.package_snapshot.checklist_snapshot.length,
      evidenceRecords: pack.evidence.length,
      expiresAt: row.expiresAt,
    },
  };
}

export async function readAuditOfflinePack(
  amoCode: string,
  auditId: string,
): Promise<AuditOfflinePack | null> {
  const scope = currentOfflineScope();
  const db = await openDb();
  try {
    const transaction = db.transaction(STORE, "readonly");
    const row = await requestResult(
      transaction.objectStore(STORE).get(packKey(scope, auditId)),
    ) as StoredAuditOfflinePack | undefined;
    await transactionDone(transaction);
    if (!row || row.scope !== scope || row.amoCode !== amoCode) return null;
    if (row.expiresAt != null && row.expiresAt <= Date.now()) return null;
    return decryptDeviceValue<AuditOfflinePack>(row.encrypted);
  } finally {
    db.close();
  }
}

export async function auditOfflinePackStatus(
  amoCode: string,
  auditId: string,
): Promise<AuditOfflinePackStatus> {
  const scope = currentOfflineScope();
  const db = await openDb();
  try {
    const transaction = db.transaction(STORE, "readonly");
    const row = await requestResult(
      transaction.objectStore(STORE).get(packKey(scope, auditId)),
    ) as StoredAuditOfflinePack | undefined;
    await transactionDone(transaction);
    if (!row || row.scope !== scope || row.amoCode !== amoCode) {
      return { ready: false, storedAt: null, verifiedAt: null, workPackageSha256: null, checklistItems: 0, evidenceRecords: 0, expiresAt: null };
    }
    if (row.expiresAt != null && row.expiresAt <= Date.now()) {
      return { ready: false, storedAt: row.storedAt, verifiedAt: row.verifiedAt, workPackageSha256: row.workPackageSha256, checklistItems: 0, evidenceRecords: 0, expiresAt: row.expiresAt };
    }
    const pack = await decryptDeviceValue<AuditOfflinePack>(row.encrypted);
    return {
      ready: true,
      storedAt: row.storedAt,
      verifiedAt: row.verifiedAt,
      workPackageSha256: row.workPackageSha256,
      checklistItems: pack.work_package.package_snapshot.checklist_snapshot.length,
      evidenceRecords: pack.evidence.length,
      expiresAt: row.expiresAt,
    };
  } finally {
    db.close();
  }
}

export async function removeAuditOfflinePack(auditId: string): Promise<void> {
  const scope = currentOfflineScope();
  const db = await openDb();
  try {
    const transaction = db.transaction(STORE, "readwrite");
    transaction.objectStore(STORE).delete(packKey(scope, auditId));
    await transactionDone(transaction);
  } finally {
    db.close();
  }
}
