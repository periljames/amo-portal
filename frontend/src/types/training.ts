// src/types/training.ts
// Shared types for the Training module.
// Mirrors backend/amodb/apps/training/schemas.py as closely as possible.

export type TrainingEventStatus = "PLANNED" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED";

export type TrainingParticipantStatus =
  | "INVITED"
  | "CONFIRMED"
  | "ATTENDED"
  | "NO_SHOW"
  | "CANCELLED"
  | "SCHEDULED"
  | "DEFERRED";

export type DeferralStatus = "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED";

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

export type TrainingRequirementScope = "ALL" | "DEPARTMENT" | "JOB_ROLE" | "USER";
export type TrainingRecordVerificationStatus = "PENDING" | "VERIFIED" | "REJECTED";

export interface TrainingCourseBase {
  course_id: string;
  course_name: string;
  frequency_months: number | null;
  category?: string | null;
  category_raw?: string | null;
  status?: string;
  scope?: string | null;
  kind?: string | null;
  delivery_method?: string | null;
  regulatory_reference?: string | null;
  default_provider?: string | null;
  default_duration_days?: number | null;
  is_mandatory: boolean;
  mandatory_for_all: boolean;
  prerequisite_course_id?: string | null;
  is_active: boolean;
}

export interface TrainingCourseCreate extends Omit<TrainingCourseBase, "is_active"> {}

export interface TrainingCourseUpdate {
  course_name?: string;
  frequency_months?: number | null;
  category?: string | null;
  category_raw?: string | null;
  status?: string;
  scope?: string | null;
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
  id: string;
  amo_id: string;
  created_by_user_id: string | null;
  updated_by_user_id: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface TrainingRequirementCreate {
  course_pk: string;
  scope: TrainingRequirementScope;
  department_code?: string | null;
  job_role?: string | null;
  user_id?: string | null;
  is_mandatory: boolean;
  is_active: boolean;
  effective_from?: string | null;
  effective_to?: string | null;
}

export interface TrainingRequirementRead extends TrainingRequirementCreate {
  id: string;
  amo_id: string;
  created_by_user_id?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface CourseImportRowIssue {
  row_number: number;
  course_id?: string | null;
  reason: string;
}

export interface CourseImportSummary {
  dry_run: boolean;
  total_rows: number;
  created_courses: number;
  updated_courses: number;
  created_requirements: number;
  updated_requirements: number;
  skipped_rows: number;
  issues: CourseImportRowIssue[];
}

export interface TrainingRecordImportChange {
  field: string;
  label: string;
  old_value?: string | null;
  new_value?: string | null;
}

export interface TrainingRecordImportRowIssue {
  row_number: number;
  legacy_record_id?: string | null;
  person_id?: string | null;
  course_id?: string | null;
  reason: string;
}

export interface TrainingRecordImportRowPreview {
  row_number: number;
  legacy_record_id?: string | null;
  person_id?: string | null;
  person_name?: string | null;
  course_id?: string | null;
  course_name?: string | null;
  completion_date?: string | null;
  next_due_date?: string | null;
  days_to_due?: number | null;
  source_status?: string | null;
  action: "CREATE" | "UPDATE" | "UNCHANGED" | "SKIP" | string;
  matched_user_id?: string | null;
  matched_user_name?: string | null;
  matched_user_active?: boolean | null;
  matched_course_pk?: string | null;
  matched_course_name?: string | null;
  existing_record_id?: string | null;
  changes: TrainingRecordImportChange[];
  reason?: string | null;
}

export interface TrainingRecordImportSummary {
  dry_run: boolean;
  total_rows: number;
  created_records: number;
  updated_records: number;
  unchanged_rows: number;
  skipped_rows: number;
  matched_inactive_rows: number;
  issues: TrainingRecordImportRowIssue[];
  preview_rows: TrainingRecordImportRowPreview[];
}

// ---------------------------------------------------------------------------
// EVENTS
// ---------------------------------------------------------------------------

export interface TrainingEventBase {
  title: string;
  location: string | null;
  provider: string | null;
  starts_on: string;
  ends_on: string | null;
  status: TrainingEventStatus;
  notes: string | null;
}

export interface TrainingEventCreate {
  course_pk: string;
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
  course_id: string;
  created_by_user_id: string | null;
  created_at?: string;
  updated_at?: string;
}

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
  notes?: string | null;
  deferral_request_id?: string | null;
}

export interface TrainingEventParticipantUpdate {
  status?: TrainingParticipantStatus;
  attendance_note?: string | null;
  notes?: string | null;
  deferral_request_id?: string | null;
  attendance_marked_at?: string | null;
  attendance_marked_by_user_id?: string | null;
  attended_at?: string | null;
}

export interface TrainingEventParticipantRead extends TrainingEventParticipantBase {
  id: string;
  amo_id: string;
  event_id: string;
  user_id: string;
  notes?: string | null;
  attendance_marked_at?: string | null;
  attendance_marked_by_user_id?: string | null;
  attended_at?: string | null;
  created_at?: string;
  updated_at?: string;
}

// ---------------------------------------------------------------------------
// TRAINING RECORDS
// ---------------------------------------------------------------------------

export interface TrainingRecordBase {
  completion_date: string;
  valid_until: string | null;
  hours_completed: number | null;
  exam_score: number | null;
  certificate_reference: string | null;
  remarks: string | null;
  is_manual_entry: boolean;
}

export interface TrainingRecordCreate {
  user_id: string;
  course_pk: string;
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
  course_code?: string | null;
  course_name?: string | null;
  user_staff_code?: string | null;
  user_full_name?: string | null;
  created_by_user_id: string | null;
  created_at?: string;
  updated_at?: string;
  verification_status?: TrainingRecordVerificationStatus;
  verified_at?: string | null;
  verified_by_user_id?: string | null;
  verification_comment?: string | null;
}

// ---------------------------------------------------------------------------
// DEFERRALS
// ---------------------------------------------------------------------------

export interface TrainingDeferralRequestBase {
  original_due_date: string;
  requested_new_due_date: string;
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
// STATUS / DASHBOARD
// ---------------------------------------------------------------------------

export interface TrainingStatusItem {
  course_id: string;
  course_name: string;
  frequency_months: number | null;
  last_completion_date: string | null;
  valid_until: string | null;
  extended_due_date: string | null;
  days_until_due: number | null;
  status: TrainingStatusLabel | string;
  upcoming_event_id: string | null;
  upcoming_event_date: string | null;
}

export interface TrainingAccessState {
  user_id: string;
  portal_locked: boolean;
  portal_lock_reason?: string | null;
  crs_blocked: boolean;
  overdue_mandatory_count: number;
  due_soon_mandatory_count: number;
  deferred_mandatory_count: number;
  not_done_mandatory_count: number;
  ok_mandatory_count: number;
  upcoming_scheduled_count: number;
}

export interface TrainingDashboardSummary {
  total_mandatory_records: number;
  ok_count: number;
  due_soon_count: number;
  overdue_count: number;
  deferred_count: number;
  scheduled_count: number;
  not_done_count: number;
}
