// src/services/training.ts
// - Training service for AMO Portal.
// - Uses generic HTTP helpers from src/services/crs.ts (apiGet/apiPost).
// - All calls are AMO-scoped via backend (amo_id derived from JWT).
//
// Backend endpoints (router: backend/amodb/apps/training/router.py):
//   * GET  /training/courses
//   * GET  /training/courses/:course_pk
//   * POST /training/courses
//   * PUT  /training/courses/:course_pk
//
//   * GET  /training/events
//   * POST /training/events
//   * PUT  /training/events/:event_id
//
//   * POST /training/event-participants
//   * PUT  /training/event-participants/:participant_id
//
//   * GET  /training/records
//   * POST /training/records
//
//   * POST /training/deferrals
//   * PUT  /training/deferrals/:deferral_id
//
//   * GET  /training/status/me
//   * GET  /training/status/users/:user_id
//
// Permissions:
//   - Read endpoints use authHeaders() (any logged-in user in same AMO).
//   - Mutating endpoints require Quality / AMO Admin / Superuser etc.
//     Enforcement lives in backend _require_training_editor.

import { apiGet, apiPost } from "./crs";
import { authHeaders, handleAuthFailure } from "./auth";
import { getApiBaseUrl } from "./config";

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

import type {
  TrainingCourseRead,
  TrainingCourseCreate,
  TrainingCourseUpdate,
  TrainingEventRead,
  TrainingEventCreate,
  TrainingEventUpdate,
  TrainingEventParticipantRead,
  TrainingEventParticipantCreate,
  TrainingEventParticipantUpdate,
  TrainingRecordRead,
  TrainingRecordCreate,
  TrainingDeferralRequestRead,
  TrainingDeferralRequestCreate,
  TrainingDeferralRequestUpdate,
  TrainingStatusItem,
  TrainingNotificationRead,
  TrainingNotificationMarkRead,
  CourseImportSummary,
  TrainingAccessState,
  TrainingRequirementRead,
  TrainingRequirementCreate,
  TrainingRequirementUpdate,
  TrainingRecordImportSummary,
} from "../types/training";

export type TrainingFileReviewStatus = "PENDING" | "APPROVED" | "REJECTED";

export type TrainingFileRead = {
  id: string;
  amo_id: string;
  owner_user_id: string;
  kind: string;
  course_id?: string | null;
  event_id?: string | null;
  record_id?: string | null;
  deferral_request_id?: string | null;
  original_filename: string;
  content_type?: string | null;
  size_bytes?: number | null;
  sha256?: string | null;
  storage_path: string;
  review_status: TrainingFileReviewStatus;
  reviewed_at?: string | null;
  reviewed_by_user_id?: string | null;
  review_comment?: string | null;
  uploaded_by_user_id?: string | null;
  uploaded_at: string;
};

export type TransferProgress = {
  loadedBytes: number;
  totalBytes?: number;
  percent?: number;
  megaBytesPerSecond: number;
  megaBitsPerSecond: number;
};

function applyXhrHeaders(xhr: XMLHttpRequest, headersInit?: HeadersInit): void {
  const headers = new Headers(headersInit);
  headers.forEach((value, key) => {
    xhr.setRequestHeader(key, value);
  });
}

// ---------------------------------------------------------------------------
// COURSES
// ---------------------------------------------------------------------------

export interface ListCoursesParams {
  include_inactive?: boolean;
}

/**
 * List training courses for the current AMO.
 */
export async function listTrainingCourses(
  params: ListCoursesParams = {},
): Promise<TrainingCourseRead[]> {
  const sp = new URLSearchParams();
  if (params.include_inactive) {
    sp.set("include_inactive", "true");
  }

  const qs = sp.toString();
  const path = qs ? `/training/courses?${qs}` : "/training/courses";

  return apiGet<TrainingCourseRead[]>(path, {
    headers: authHeaders(),
  });
}

/**
 * Get a single training course by backend PK.
 */
export async function getTrainingCourse(
  coursePk: string,
): Promise<TrainingCourseRead> {
  return apiGet<TrainingCourseRead>(`/training/courses/${encodeURIComponent(coursePk)}`, {
    headers: authHeaders(),
  });
}

/**
 * Create a new training course (Quality / AMO admin only).
 */
export async function createTrainingCourse(
  payload: TrainingCourseCreate,
): Promise<TrainingCourseRead> {
  return apiPost<TrainingCourseRead>("/training/courses", payload, {
    headers: authHeaders(),
  });
}

/**
 * Update an existing training course (Quality / AMO admin only).
 */
export async function updateTrainingCourse(
  coursePk: string,
  payload: TrainingCourseUpdate,
): Promise<TrainingCourseRead> {
  // There is no dedicated apiPut helper exported, so we reuse apiPost
  // with the conventional REST pattern of using PUT at the fetch layer
  // (see implementation of request<T> in crs.ts).
  return apiPost<TrainingCourseRead>(
    `/training/courses/${encodeURIComponent(coursePk)}`,
    payload,
    {
      method: "PUT",
      headers: authHeaders(),
    } as RequestInit,
  );
}

export async function importTrainingCoursesWorkbook(
  file: File,
  opts?: { dryRun?: boolean; sheetName?: string; onProgress?: (progress: TransferProgress) => void }
): Promise<CourseImportSummary> {
  const dryRun = opts?.dryRun ?? true;
  const sheetName = opts?.sheetName ?? "Courses";
  const onProgress = opts?.onProgress;
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const startedAt = performance.now();
    const apiBaseUrl = getApiBaseUrl();
    const qs = new URLSearchParams({
      dry_run: String(dryRun),
      sheet_name: sheetName,
    });
    xhr.open("POST", `${apiBaseUrl}/training/courses/import?${qs.toString()}`);
    applyXhrHeaders(xhr, authHeaders());

    xhr.upload.addEventListener("progress", (event) => {
      if (!onProgress) return;
      const total = event.lengthComputable ? event.total : undefined;
      onProgress(buildSpeed(event.loaded, total, startedAt));
    });

    xhr.addEventListener("load", () => {
      if (xhr.status === 401) {
        handleAuthFailure("expired");
        reject(new Error("Session expired. Please sign in again."));
        return;
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(xhr.responseText || `Request failed (${xhr.status})`));
        return;
      }
      try {
        resolve(JSON.parse(xhr.responseText) as CourseImportSummary);
      } catch {
        reject(new Error("Invalid courses import response."));
      }
    });
    xhr.addEventListener("error", () => reject(new Error("Network error while importing courses workbook.")));

    const fd = new FormData();
    fd.append("file", file);
    xhr.send(fd);
  });
}



export async function importTrainingRecordsWorkbook(
  file: File,
  opts?: { dryRun?: boolean; sheetName?: string; onProgress?: (progress: TransferProgress) => void }
): Promise<TrainingRecordImportSummary> {
  const dryRun = opts?.dryRun ?? true;
  const sheetName = opts?.sheetName ?? "Training";
  const onProgress = opts?.onProgress;
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const startedAt = performance.now();
    const apiBaseUrl = getApiBaseUrl();
    const qs = new URLSearchParams({
      dry_run: String(dryRun),
      sheet_name: sheetName,
    });
    xhr.open("POST", `${apiBaseUrl}/training/records/import?${qs.toString()}`);
    applyXhrHeaders(xhr, authHeaders());

    xhr.upload.addEventListener("progress", (event) => {
      if (!onProgress) return;
      const total = event.lengthComputable ? event.total : undefined;
      onProgress(buildSpeed(event.loaded, total, startedAt));
    });

    xhr.addEventListener("load", () => {
      if (xhr.status === 401) {
        handleAuthFailure("expired");
        reject(new Error("Session expired. Please sign in again."));
        return;
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(xhr.responseText || `Request failed (${xhr.status})`));
        return;
      }
      try {
        resolve(JSON.parse(xhr.responseText) as TrainingRecordImportSummary);
      } catch {
        reject(new Error("Invalid training records import response."));
      }
    });
    xhr.addEventListener("error", () => reject(new Error("Network error while importing training records workbook.")));

    const fd = new FormData();
    fd.append("file", file);
    xhr.send(fd);
  });
}

// ---------------------------------------------------------------------------
// REQUIREMENTS
// ---------------------------------------------------------------------------


export interface ListTrainingRequirementsParams {
  include_inactive?: boolean;
}

export async function listTrainingRequirements(
  params: ListTrainingRequirementsParams = {},
): Promise<TrainingRequirementRead[]> {
  const sp = new URLSearchParams();
  if (params.include_inactive) sp.set("include_inactive", "true");
  const qs = sp.toString();
  const path = qs ? `/training/requirements?${qs}` : "/training/requirements";
  return apiGet<TrainingRequirementRead[]>(path, { headers: authHeaders() });
}

export async function createTrainingRequirement(
  payload: TrainingRequirementCreate,
): Promise<TrainingRequirementRead> {
  return apiPost<TrainingRequirementRead>("/training/requirements", payload, {
    headers: authHeaders(),
  });
}

export async function updateTrainingRequirement(
  requirementId: string,
  payload: TrainingRequirementUpdate,
): Promise<TrainingRequirementRead> {
  return apiPost<TrainingRequirementRead>(
    `/training/requirements/${encodeURIComponent(requirementId)}`,
    payload,
    {
      method: "PUT",
      headers: authHeaders(),
    } as RequestInit,
  );
}

export async function listTrainingEventParticipants(eventId: string): Promise<TrainingEventParticipantRead[]> {
  return apiGet<TrainingEventParticipantRead[]>(`/training/events/${encodeURIComponent(eventId)}/participants`, {
    headers: authHeaders(),
  });
}

// ---------------------------------------------------------------------------
// EVENTS
// ---------------------------------------------------------------------------

export interface ListEventsParams {
  course_pk?: string;
  from_date?: string; // ISO date
  to_date?: string;   // ISO date
}

/**
 * List training events for the current AMO with optional filters.
 */
export async function listTrainingEvents(
  params: ListEventsParams = {},
): Promise<TrainingEventRead[]> {
  const sp = new URLSearchParams();

  if (params.course_pk) sp.set("course_pk", params.course_pk);
  if (params.from_date) sp.set("from_date", params.from_date);
  if (params.to_date) sp.set("to_date", params.to_date);

  const qs = sp.toString();
  const path = qs ? `/training/events?${qs}` : "/training/events";

  return apiGet<TrainingEventRead[]>(path, {
    headers: authHeaders(),
  });
}

/**
 * Create a training event (Quality / AMO admin only).
 */
export async function createTrainingEvent(
  payload: TrainingEventCreate,
): Promise<TrainingEventRead> {
  return apiPost<TrainingEventRead>("/training/events", payload, {
    headers: authHeaders(),
  });
}

/**
 * Update a training event (Quality / AMO admin only).
 */
export async function updateTrainingEvent(
  eventId: string,
  payload: TrainingEventUpdate,
): Promise<TrainingEventRead> {
  return apiPost<TrainingEventRead>(
    `/training/events/${encodeURIComponent(eventId)}`,
    payload,
    {
      method: "PUT",
      headers: authHeaders(),
    } as RequestInit,
  );
}

// ---------------------------------------------------------------------------
// EVENT PARTICIPANTS
// ---------------------------------------------------------------------------

/**
 * Add a participant to a training event (Quality / AMO admin only).
 */
export async function addTrainingEventParticipant(
  payload: TrainingEventParticipantCreate,
): Promise<TrainingEventParticipantRead> {
  return apiPost<TrainingEventParticipantRead>(
    "/training/event-participants",
    payload,
    {
      headers: authHeaders(),
    },
  );
}

/**
 * Update a participant's status in an event (Quality / AMO admin only).
 */
export async function updateTrainingEventParticipant(
  participantId: string,
  payload: TrainingEventParticipantUpdate,
): Promise<TrainingEventParticipantRead> {
  return apiPost<TrainingEventParticipantRead>(
    `/training/event-participants/${encodeURIComponent(participantId)}`,
    payload,
    {
      method: "PUT",
      headers: authHeaders(),
    } as RequestInit,
  );
}

// ---------------------------------------------------------------------------
// TRAINING FILES (EVIDENCE DOWNLOADS)
// ---------------------------------------------------------------------------

function buildSpeed(
  loadedBytes: number,
  totalBytes: number | undefined,
  startedAt: number
): TransferProgress {
  const elapsedSeconds = Math.max((performance.now() - startedAt) / 1000, 0.001);
  const megaBytesPerSecond = loadedBytes / (1024 * 1024) / elapsedSeconds;
  const megaBitsPerSecond = megaBytesPerSecond * 8;
  const percent = totalBytes ? Math.min((loadedBytes / totalBytes) * 100, 100) : undefined;
  return {
    loadedBytes,
    totalBytes,
    percent,
    megaBytesPerSecond,
    megaBitsPerSecond,
  };
}

export interface ListTrainingFilesParams {
  owner_user_id?: string;
  kind?: string;
  review_status?: TrainingFileReviewStatus;
}

export async function listTrainingFiles(params: ListTrainingFilesParams = {}): Promise<TrainingFileRead[]> {
  const sp = new URLSearchParams();
  if (params.owner_user_id) sp.set("owner_user_id", params.owner_user_id);
  if (params.kind) sp.set("kind", params.kind);
  if (params.review_status) sp.set("review_status", params.review_status);
  const qs = sp.toString();
  const path = qs ? `/training/files?${qs}` : "/training/files";
  return apiGet<TrainingFileRead[]>(path, {
    headers: authHeaders(),
  });
}

export async function uploadTrainingFile(payload: FormData): Promise<TrainingFileRead> {
  return apiPost<TrainingFileRead>("/training/files/upload", payload, {
    method: "POST",
    headers: authHeaders(),
  } as RequestInit);
}

export async function downloadTrainingFile(
  fileId: string,
  onProgress?: (progress: TransferProgress) => void
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const startedAt = performance.now();
    const apiBaseUrl = getApiBaseUrl();
    xhr.open(
      "GET",
      `${apiBaseUrl}/training/files/${encodeURIComponent(fileId)}/download`,
    );
    applyXhrHeaders(xhr, authHeaders());
    xhr.responseType = "blob";

    xhr.addEventListener("progress", (event) => {
      if (!onProgress) return;
      const total = event.lengthComputable ? event.total : undefined;
      onProgress(buildSpeed(event.loaded, total, startedAt));
    });

    xhr.addEventListener("load", () => {
      if (xhr.status === 401) {
        handleAuthFailure("expired");
        reject(new Error("Session expired. Please sign in again."));
        return;
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        const message = xhr.responseText || `Request failed (${xhr.status})`;
        reject(new Error(message));
        return;
      }
      resolve(xhr.response as Blob);
    });

    xhr.addEventListener("error", () => {
      reject(new Error("Network error while downloading training file."));
    });

    xhr.send();
  });
}

export interface TrainingRecordPdfWarmResponse {
  queued: boolean;
  ready: boolean;
}

export async function warmTrainingUserRecordPdf(userId: string): Promise<TrainingRecordPdfWarmResponse> {
  return apiPost<TrainingRecordPdfWarmResponse>(
    `/training/users/${encodeURIComponent(userId)}/record-pdf/warm`,
    {},
    {
      headers: authHeaders(),
    },
  );
}

export async function downloadTrainingUserRecordPdf(userId: string): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const apiBaseUrl = getApiBaseUrl();
    xhr.open(
      "GET",
      `${apiBaseUrl}/training/users/${encodeURIComponent(userId)}/record-pdf`,
    );
    applyXhrHeaders(xhr, authHeaders());
    xhr.responseType = "blob";

    xhr.addEventListener("load", () => {
      if (xhr.status === 401) {
        handleAuthFailure("expired");
        reject(new Error("Session expired. Please sign in again."));
        return;
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        const message = xhr.responseText || `Request failed (${xhr.status})`;
        reject(new Error(message));
        return;
      }
      resolve(xhr.response as Blob);
    });

    xhr.addEventListener("error", () => {
      reject(new Error("Network error while downloading individual training record."));
    });

    xhr.send();
  });
}

export async function downloadTrainingUserEvidencePack(userId: string): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const apiBaseUrl = getApiBaseUrl();
    xhr.open(
      "GET",
      `${apiBaseUrl}/training/users/${encodeURIComponent(userId)}/evidence-pack`,
    );
    applyXhrHeaders(xhr, authHeaders());
    xhr.responseType = "blob";

    xhr.addEventListener("load", () => {
      if (xhr.status === 401) {
        handleAuthFailure("expired");
        reject(new Error("Session expired. Please sign in again."));
        return;
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        const message = xhr.responseText || `Request failed (${xhr.status})`;
        reject(new Error(message));
        return;
      }
      resolve(xhr.response as Blob);
    });

    xhr.addEventListener("error", () => {
      reject(new Error("Network error while downloading training evidence pack."));
    });

    xhr.send();
  });
}

// ---------------------------------------------------------------------------
 // TRAINING RECORDS
// ---------------------------------------------------------------------------

export interface ListTrainingRecordsParams {
  user_id?: string;
  course_pk?: string;
}

/**
 * List training completion records for the current AMO.
 *
 * Supports server filtering; avoid loading records for all users when viewing a single profile.
 */
export async function listTrainingRecords(
  params: ListTrainingRecordsParams = {},
): Promise<TrainingRecordRead[]> {
  const sp = new URLSearchParams();
  if (params.user_id) sp.set("user_id", params.user_id);
  if (params.course_pk) sp.set("course_pk", params.course_pk);
  if (!sp.has("limit")) sp.set("limit", "1000");

  const qs = sp.toString();
  const path = qs ? `/training/records?${qs}` : "/training/records?limit=1000";

  try {
    return await apiGet<TrainingRecordRead[]>(path, {
      headers: authHeaders(),
    });
  } catch (error: any) {
    const message = String(error?.message || "").toLowerCase();
    if (message.includes("deadlock")) {
      await delay(120);
      return apiGet<TrainingRecordRead[]>(path, {
        headers: authHeaders(),
      });
    }
    throw error;
  }
}

/**
 * Create a training completion record (Quality / AMO admin only).
 */
export async function createTrainingRecord(
  payload: TrainingRecordCreate,
): Promise<TrainingRecordRead> {
  return apiPost<TrainingRecordRead>("/training/records", payload, {
    headers: authHeaders(),
  });
}

// ---------------------------------------------------------------------------
// DEFERRALS (QWI-026)
// ---------------------------------------------------------------------------

/**
 * Request a training deferral.
 * Any active user can request their own; Quality/Admin can request for others.
 */
export async function createTrainingDeferralRequest(
  payload: TrainingDeferralRequestCreate,
): Promise<TrainingDeferralRequestRead> {
  return apiPost<TrainingDeferralRequestRead>("/training/deferrals", payload, {
    headers: authHeaders(),
  });
}

/**
 * Approve / reject / amend a deferral request (Quality / AMO admin only).
 */
export async function updateTrainingDeferralRequest(
  deferralId: string,
  payload: TrainingDeferralRequestUpdate,
): Promise<TrainingDeferralRequestRead> {
  return apiPost<TrainingDeferralRequestRead>(
    `/training/deferrals/${encodeURIComponent(deferralId)}`,
    payload,
    {
      method: "PUT",
      headers: authHeaders(),
    } as RequestInit,
  );
}

/**
 * List deferral requests for the current user.
 */
export async function listMyTrainingDeferrals(): Promise<TrainingDeferralRequestRead[]> {
  return apiGet<TrainingDeferralRequestRead[]>("/training/deferrals/me", {
    headers: authHeaders(),
  });
}

export interface ListTrainingDeferralsParams {
  status?: "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED";
  user_id?: string;
  limit?: number;
  offset?: number;
}

export async function listTrainingDeferrals(
  params: ListTrainingDeferralsParams = {},
): Promise<TrainingDeferralRequestRead[]> {
  const sp = new URLSearchParams();
  if (params.status) sp.set("status", params.status);
  if (params.user_id) sp.set("user_id", params.user_id);
  if (params.limit) sp.set("limit", String(params.limit));
  if (params.offset) sp.set("offset", String(params.offset));
  const qs = sp.toString();
  const path = qs ? `/training/deferrals?${qs}` : "/training/deferrals";
  return apiGet<TrainingDeferralRequestRead[]>(path, {
    headers: authHeaders(),
  });
}

// ---------------------------------------------------------------------------
// STATUS VIEWS
// ---------------------------------------------------------------------------

/**
 * Training status for the current logged-in user.
 */
export async function getMyTrainingStatus(): Promise<TrainingStatusItem[]> {
  return apiGet<TrainingStatusItem[]>("/training/status/me", {
    headers: authHeaders(),
  });
}

export interface TrainingStatusBulkResponse {
  users: Record<string, TrainingStatusItem[]>;
}

export async function getBulkTrainingStatusForUsers(
  userIds: string[],
): Promise<TrainingStatusBulkResponse> {
  try {
    return await apiPost<TrainingStatusBulkResponse>(
      "/training/status/users/bulk",
      { user_ids: userIds },
      {
        headers: authHeaders(),
      },
    );
  } catch {
    const users: Record<string, TrainingStatusItem[]> = {};
    await Promise.all(
      userIds.map(async (userId) => {
        try {
          users[userId] = await getUserTrainingStatus(userId);
        } catch {
          users[userId] = [];
        }
      }),
    );
    return { users };
  }
}

/**
 * Training status for a specific user (Quality / AMO admin only).
 */
export async function getUserTrainingStatus(
  userId: string,
): Promise<TrainingStatusItem[]> {
  return apiGet<TrainingStatusItem[]>(
    `/training/status/users/${encodeURIComponent(userId)}`,
    {
      headers: authHeaders(),
    },
  );
}

export async function getMyTrainingAccessState(): Promise<TrainingAccessState> {
  return apiGet<TrainingAccessState>("/training/status/access/me", {
    headers: authHeaders(),
  });
}

export async function getUserTrainingAccessState(userId: string): Promise<TrainingAccessState> {
  return apiGet<TrainingAccessState>(`/training/status/access/users/${encodeURIComponent(userId)}`, {
    headers: authHeaders(),
  });
}

export async function runTrainingNotificationSweep(): Promise<{ notifications_created: number }> {
  return apiPost<{ notifications_created: number }>("/training/compliance/notifications/sweep", {}, {
    headers: authHeaders(),
  });
}

// ---------------------------------------------------------------------------
// NOTIFICATIONS
// ---------------------------------------------------------------------------

export interface ListTrainingNotificationsParams {
  unread_only?: boolean;
  limit?: number;
  offset?: number;
}

export async function listTrainingNotifications(
  params: ListTrainingNotificationsParams = {},
): Promise<TrainingNotificationRead[]> {
  const sp = new URLSearchParams();
  if (params.unread_only) sp.set("unread_only", "true");
  if (params.limit) sp.set("limit", String(params.limit));
  if (params.offset) sp.set("offset", String(params.offset));
  const qs = sp.toString();
  const path = qs ? `/training/notifications/me?${qs}` : "/training/notifications/me";
  return apiGet<TrainingNotificationRead[]>(path, {
    headers: authHeaders(),
  });
}

export async function markTrainingNotificationRead(
  notificationId: string,
  payload: TrainingNotificationMarkRead,
): Promise<TrainingNotificationRead> {
  return apiPost<TrainingNotificationRead>(
    `/training/notifications/${encodeURIComponent(notificationId)}/read`,
    payload,
    {
      method: "PUT",
      headers: authHeaders(),
    } as RequestInit,
  );
}

export async function markAllTrainingNotificationsRead(): Promise<{ ok: boolean }> {
  return apiPost<{ ok: boolean }>(
    "/training/notifications/me/read-all",
    {},
    {
      headers: authHeaders(),
    },
  );
}

export async function listTrainingCertificates(userId?: string): Promise<TrainingRecordRead[]> {
  const path = userId
    ? `/training/certificates?user_id=${encodeURIComponent(userId)}`
    : "/training/certificates";
  return apiGet<TrainingRecordRead[]>(path, { headers: authHeaders() });
}

export async function issueTrainingCertificate(recordId: string): Promise<TrainingRecordRead> {
  return apiPost<TrainingRecordRead>(
    `/training/certificates/issue/${encodeURIComponent(recordId)}`,
    {},
    { headers: authHeaders() },
  );
}

export type PublicCertificateVerification = {
  status: "VALID" | "EXPIRED" | "NOT_FOUND" | "MALFORMED";
  certificate_number: string;
  trainee_name?: string;
  course_title?: string;
  issue_date?: string;
  valid_until?: string | null;
  issuer?: string;
};

export async function verifyCertificatePublic(certificateNumber: string): Promise<PublicCertificateVerification> {
  const base = getApiBaseUrl() || (import.meta.env.DEV ? (import.meta.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8080") : "");
  const url = `${base}/public/certificates/verify/${encodeURIComponent(certificateNumber)}`;
  const res = await fetch(url, { method: "GET" });
  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("Verification service unavailable");
  }
  const data = (await res.json()) as PublicCertificateVerification;
  if (!res.ok) {
    throw new Error((data as any)?.message || "Verification service unavailable");
  }
  return data;
}
