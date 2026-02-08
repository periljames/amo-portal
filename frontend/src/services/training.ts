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

export async function listTrainingFiles(): Promise<TrainingFileRead[]> {
  return apiGet<TrainingFileRead[]>("/training/files", {
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
    const headers = authHeaders();
    Object.entries(headers).forEach(([key, value]) => {
      xhr.setRequestHeader(key, value);
    });
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

export async function downloadTrainingUserEvidencePack(userId: string): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const apiBaseUrl = getApiBaseUrl();
    xhr.open(
      "GET",
      `${apiBaseUrl}/training/users/${encodeURIComponent(userId)}/evidence-pack`,
    );
    const headers = authHeaders();
    Object.entries(headers).forEach(([key, value]) => {
      xhr.setRequestHeader(key, value);
    });
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
 * NOTE: Backend currently does not support pagination on this endpoint;
 * if the dataset becomes massive, we will extend the API with skip/limit.
 */
export async function listTrainingRecords(
  params: ListTrainingRecordsParams = {},
): Promise<TrainingRecordRead[]> {
  const sp = new URLSearchParams();
  if (params.user_id) sp.set("user_id", params.user_id);
  if (params.course_pk) sp.set("course_pk", params.course_pk);

  const qs = sp.toString();
  const path = qs ? `/training/records?${qs}` : "/training/records";

  return apiGet<TrainingRecordRead[]>(path, {
    headers: authHeaders(),
  });
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
