// src/types/training.ts
// Shared types for the Training module.
// Mirrors backend/amodb/apps/training/schemas.py as closely as possible.

export type TrainingEventStatus = "PLANNED" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED";

export type TrainingParticipantStatus =
  | "INVITED"
  | "CONFIRMED"
  | "ATTENDED"
  | "NO_SHOW"
  | "CANCELLED";

export type DeferralStatus = "PENDING" | "APPROVED" | "REJECTED";

export type DeferralReasonCategory =
  | "ILLNESS"
  | "OPERATIONAL_REQUIREMENTS"
  | "PERSONAL_EMERGENCY"
  | "PROVIDER_CANCELLATION"
  | "SYSTEM_FAILURE"
  | "OTHER";

export type TrainingStatusLabel =
  | "OK"
  | "DUE_SOON"
  | "OVERDUE"
  | "DEFERRED"
  | "SCHEDULED_ONLY"
  | "NOT_DONE";

export type TrainingNotificationSeverity = "INFO" | "ACTION_REQUIRED" | "WARNING";

export interface TrainingCourseBase {
  course_id: string;            // e.g. "HF-REF"
  course_name: string;          // e.g. "Human Factors in Aviation (Refresher)"
  frequency_months: number | null;

  category?: string | null;     // e.g. "REGULATORY", "INTERNAL"
  kind?: string | null;         // e.g. "INITIAL", "REFRESHER"
  delivery_method?: string | null; // e.g. "CLASSROOM", "ONLINE", "CBT"

  regulatory_reference?: string | null; // e.g. "KCARs Part II", "IOSA"
  default_provider?: string | null;     // Safarilink / external provider name
  default_duration_days?: number | null;

  is_mandatory: boolean;
  mandatory_for_all: boolean;

  // For chains like: Induction -> MPM, or Initial -> Refresher
  prerequisite_course_id?: string | null;

  is_active: boolean;
}

export interface TrainingCourseCreate extends Omit<TrainingCourseBase, "is_active"> {
  // is_active default is true server-side
}

export interface TrainingCourseUpdate {
  course_name?: string;
  frequency_months?: number | null;
  category?: string | null;
  kind?: string | null;
  delivery_method?: string | null;
  regulatory_reference?: string | null;
  default_provider?: string | null;
  default_duration_days?: number | null;
  is_mandatory?: boolean;
  mandatory_for_all?: boolean;
  prerequisite_course_id?: string | null;
  is_active?: boolean;
}

export interface TrainingCourseRead extends TrainingCourseBase {
  id: string;        // backend UUID/PK
  amo_id: string;

  created_by_user_id: string | null;
  updated_by_user_id: string | null;
  created_at?: string; // ISO datetime
  updated_at?: string; // ISO datetime
}

// ---------------------------------------------------------------------------
// EVENTS
// ---------------------------------------------------------------------------

export interface TrainingEventBase {
  title: string;
  location: string | null;
  provider: string | null;
  starts_on: string;     // ISO date ("YYYY-MM-DD")
  ends_on: string | null;
  status: TrainingEventStatus;
  notes: string | null;
}

export interface TrainingEventCreate {
  course_pk: string; // TrainingCourseRead.id
  title?: string | null;
  location?: string | null;
  provider?: string | null;
  starts_on: string;
  ends_on?: string | null;
  status: TrainingEventStatus;
  notes?: string | null;
}

export interface TrainingEventUpdate {
  title?: string | null;
  location?: string | null;
  provider?: string | null;
  starts_on?: string;
  ends_on?: string | null;
  status?: TrainingEventStatus;
  notes?: string | null;
}

export interface TrainingEventRead extends TrainingEventBase {
  id: string;
  amo_id: string;
  course_id: string;          // FK to TrainingCourseRead.id
  created_by_user_id: string | null;
  created_at?: string;
  updated_at?: string;
}

// ---------------------------------------------------------------------------
// EVENT PARTICIPANTS
// ---------------------------------------------------------------------------

export interface TrainingEventParticipantBase {
  status: TrainingParticipantStatus;
  attendance_note: string | null;
  deferral_request_id: string | null;
}

export interface TrainingEventParticipantCreate {
  event_id: string;
  user_id: string;
  status: TrainingParticipantStatus;
  attendance_note?: string | null;
  deferral_request_id?: string | null;
}

export interface TrainingEventParticipantUpdate {
  status?: TrainingParticipantStatus;
  attendance_note?: string | null;
  deferral_request_id?: string | null;
}

export interface TrainingEventParticipantRead extends TrainingEventParticipantBase {
  id: string;
  event_id: string;
  user_id: string;
  created_at?: string;
  updated_at?: string;
}

// ---------------------------------------------------------------------------
// TRAINING RECORDS
// ---------------------------------------------------------------------------

export interface TrainingRecordBase {
  completion_date: string;       // ISO date
  valid_until: string | null;    // ISO date
  hours_completed: number | null;
  exam_score: number | null;
  certificate_reference: string | null;
  remarks: string | null;
  is_manual_entry: boolean;
}

export interface TrainingRecordCreate {
  user_id: string;
  course_pk: string;       // TrainingCourseRead.id
  event_id?: string | null;

  completion_date: string;
  valid_until?: string | null;

  hours_completed?: number | null;
  exam_score?: number | null;
  certificate_reference?: string | null;
  remarks?: string | null;
  is_manual_entry?: boolean;
}

export interface TrainingRecordRead extends TrainingRecordBase {
  id: string;
  amo_id: string;
  user_id: string;
  course_id: string;
  event_id: string | null;

  created_by_user_id: string | null;
  created_at?: string;
  updated_at?: string;
}

// ---------------------------------------------------------------------------
// DEFERRALS
// ---------------------------------------------------------------------------

export interface TrainingDeferralRequestBase {
  original_due_date: string;       // ISO date
  requested_new_due_date: string;  // ISO date
  reason_category: DeferralReasonCategory;
  reason_text: string | null;
}

export interface TrainingDeferralRequestCreate {
  user_id: string;
  course_pk: string;
  original_due_date: string;
  requested_new_due_date: string;
  reason_category: DeferralReasonCategory;
  reason_text?: string | null;
}

export interface TrainingDeferralRequestUpdate {
  status?: DeferralStatus;
  decision_comment?: string | null;
  requested_new_due_date?: string | null;
}

export interface TrainingDeferralRequestRead extends TrainingDeferralRequestBase {
  id: string;
  amo_id: string;
  user_id: string;
  course_id: string;

  status: DeferralStatus;
  decision_comment: string | null;
  decided_at?: string | null;
  decided_by_user_id?: string | null;

  created_at?: string;
  updated_at?: string;
}

// ---------------------------------------------------------------------------
// NOTIFICATIONS
// ---------------------------------------------------------------------------

export interface TrainingNotificationRead {
  id: string;
  amo_id: string;
  user_id: string;
  title: string;
  body?: string | null;
  severity: TrainingNotificationSeverity;
  link_path?: string | null;
  dedupe_key?: string | null;
  created_at: string;
  read_at?: string | null;
}

export interface TrainingNotificationMarkRead {
  read_at?: string | null;
}

// ---------------------------------------------------------------------------
// STATUS VIEW (per user, per course)
// ---------------------------------------------------------------------------

export interface TrainingStatusItem {
  course_id: string;                 // logical course code, e.g. "HF-REF"
  course_name: string;
  frequency_months: number | null;

  last_completion_date: string | null;   // ISO date
  valid_until: string | null;            // original validity
  extended_due_date: string | null;      // after deferral, if any
  days_until_due: number | null;

  status: TrainingStatusLabel;

  upcoming_event_id: string | null;
  upcoming_event_date: string | null;    // ISO date
}
