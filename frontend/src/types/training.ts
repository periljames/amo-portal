// src/types/training.ts
// Shared frontend types for the Training & Competence module.
// These interfaces intentionally mirror the backend training schemas while
// allowing additive backend fields without breaking pages during module rollout.

export type { QmsListResponse } from "./qms";

export type TrainingCourseCategory =
  | "HF"
  | "FTS"
  | "EWIS"
  | "SMS"
  | "TYPE"
  | "INTERNAL_TECHNICAL"
  | "QUALITY_SYSTEMS"
  | "REGULATORY"
  | "OTHER";

export type TrainingKind = "INITIAL" | "CONTINUATION" | "RECURRENT" | "REFRESHER" | "OTHER";
export type TrainingDeliveryMethod = "CLASSROOM" | "ONLINE" | "OJT" | "MIXED" | "OTHER";
export type TrainingEventStatus = "PLANNED" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED";
export type TrainingParticipantStatus = "SCHEDULED" | "INVITED" | "CONFIRMED" | "ATTENDED" | "NO_SHOW" | "CANCELLED" | "DEFERRED";
export type TrainingRequirementScope = "ALL" | "DEPARTMENT" | "JOB_ROLE" | "USER";
export type DeferralStatus = "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED";
export type DeferralReasonCategory = "ILLNESS" | "OPERATIONAL_REQUIREMENTS" | "PERSONAL_EMERGENCY" | "PROVIDER_CANCELLATION" | "SYSTEM_FAILURE" | "OTHER";
export type TrainingNotificationSeverity = "INFO" | "ACTION_REQUIRED" | "WARNING";
export type TrainingRecordVerificationStatus = "PENDING" | "VERIFIED" | "REJECTED";
export type TrainingFileKind = "CERTIFICATE" | "AMEL" | "LICENSE" | "EVIDENCE" | "OTHER";
export type TrainingFileReviewStatus = "PENDING" | "APPROVED" | "REJECTED";

export interface TrainingCourseRead {
  id: string;
  amo_id: string;
  course_id: string;
  course_pk: string;
  course_name: string;
  frequency_months?: number | null;
  category?: TrainingCourseCategory | string;
  category_raw?: string | null;
  status?: string;
  scope?: string | null;
  kind?: TrainingKind | string;
  delivery_method?: TrainingDeliveryMethod | string;
  regulatory_reference?: string | null;
  default_provider?: string | null;
  default_duration_days?: number | null;
  nominal_hours?: number | null;
  planning_lead_days?: number | null;
  candidate_requirement_text?: string | null;
  is_mandatory?: boolean;
  mandatory_for_all?: boolean;
  prerequisite_course_id?: string | null;
  is_active?: boolean;
  created_at?: string;
  updated_at?: string;
  [key: string]: any;
}

export type TrainingCourseCreate = Omit<Partial<TrainingCourseRead>, "id" | "amo_id" | "created_at" | "updated_at"> & {
  course_id: string;
  course_pk?: string;
  course_name: string;
};
export type TrainingCourseUpdate = Partial<TrainingCourseCreate>;

export interface TrainingRequirementRead {
  id: string;
  amo_id: string;
  course_id: string;
  course_pk: string;
  scope: TrainingRequirementScope;
  department_code?: string | null;
  job_role?: string | null;
  user_id?: string | null;
  is_mandatory?: boolean;
  is_active?: boolean;
  effective_from?: string | null;
  effective_to?: string | null;
  created_at?: string;
  updated_at?: string;
  course?: TrainingCourseRead | null;
  [key: string]: any;
}

export interface TrainingRequirementCreate {
  course_id?: string;
  course_pk: string;
  scope: TrainingRequirementScope;
  department_code?: string | null;
  job_role?: string | null;
  user_id?: string | null;
  is_mandatory?: boolean;
  is_active?: boolean;
  effective_from?: string | null;
  effective_to?: string | null;
}

export type TrainingRequirementUpdate = Partial<TrainingRequirementCreate>;

export interface TrainingEventRead {
  id: string;
  amo_id: string;
  course_id: string;
  course_pk?: string;
  title: string;
  location?: string | null;
  provider?: string | null;
  starts_on: string;
  ends_on?: string | null;
  status: TrainingEventStatus | string;
  notes?: string | null;
  created_by_user_id?: string | null;
  created_at?: string;
  updated_at?: string;
  course?: TrainingCourseRead | null;
  participants?: TrainingEventParticipantRead[];
  participant_count?: number;
  [key: string]: any;
}

export interface TrainingEventCreate {
  course_id: string;
  title?: string;
  location?: string | null;
  provider?: string | null;
  starts_on: string;
  ends_on?: string | null;
  status?: TrainingEventStatus;
  notes?: string | null;
  [key: string]: any;
}

export type TrainingEventUpdate = Partial<TrainingEventCreate>;

export interface TrainingEventParticipantRead {
  id: string;
  amo_id: string;
  event_id: string;
  user_id: string;
  status: TrainingParticipantStatus | string;
  attendance_note?: string | null;
  attended_at?: string | null;
  notes?: string | null;
  deferral_request_id?: string | null;
  created_at?: string;
  updated_at?: string;
  [key: string]: any;
}

export interface TrainingEventParticipantCreate {
  event_id: string;
  user_id: string;
  status?: TrainingParticipantStatus;
  notes?: string | null;
}

export type TrainingEventParticipantUpdate = Partial<Omit<TrainingEventParticipantCreate, "event_id" | "user_id">> & {
  attendance_note?: string | null;
  attended_at?: string | null;
};

export interface TrainingRecordRead {
  id: string;
  amo_id: string;
  user_id: string;
  course_id: string;
  course_pk?: string;
  course_name?: string;
  course_code?: string;
  record_status?: string;
  source_status?: string;
  superseded_by_record_id?: string | null;
  superseded_at?: string | null;
  purge_after?: string | null;
  attachment_file_id?: string | null;
  event_id?: string | null;
  completion_date: string;
  valid_until?: string | null;
  hours_completed?: number | null;
  exam_score?: number | null;
  certificate_reference?: string | null;
  remarks?: string | null;
  verification_status?: TrainingRecordVerificationStatus | string;
  verified_at?: string | null;
  verified_by_user_id?: string | null;
  verification_comment?: string | null;
  is_manual_entry?: boolean;
  created_by_user_id?: string | null;
  created_at?: string;
  course?: TrainingCourseRead | null;
  [key: string]: any;
}

export interface TrainingRecordCreate {
  user_id: string;
  course_id?: string;
  course_pk: string;
  course_name?: string;
  course_code?: string;
  record_status?: string;
  source_status?: string;
  confirm_renewal?: boolean;
  attachment_file_id?: string | null;
  event_id?: string | null;
  completion_date: string;
  valid_until?: string | null;
  hours_completed?: number | null;
  exam_score?: number | null;
  certificate_reference?: string | null;
  remarks?: string | null;
  verification_status?: TrainingRecordVerificationStatus;
  is_manual_entry?: boolean;
}

export type TrainingRecordUpdate = Partial<TrainingRecordCreate> & {
  verification_comment?: string | null;
  attachment_file_id?: string | null;
};

export interface TrainingDeferralRequestRead {
  id: string;
  amo_id: string;
  user_id: string;
  requested_by_user_id?: string | null;
  course_id: string;
  original_due_date: string;
  requested_new_due_date: string;
  reason_category: DeferralReasonCategory | string;
  reason_text?: string | null;
  status: DeferralStatus | string;
  decided_at?: string | null;
  decided_by_user_id?: string | null;
  decision_comment?: string | null;
  requested_at?: string;
  updated_at?: string;
  course?: TrainingCourseRead | null;
  [key: string]: any;
}

export interface TrainingDeferralRequestCreate {
  user_id?: string;
  course_id?: string;
  course_pk: string;
  original_due_date: string;
  requested_new_due_date: string;
  reason_category?: DeferralReasonCategory;
  reason_text?: string | null;
}

export type TrainingDeferralRequestUpdate = Partial<TrainingDeferralRequestCreate> & {
  status?: DeferralStatus;
  decision_comment?: string | null;
};

export interface TrainingStatusItem {
  course_id: string;
  course_pk?: string;
  course_name: string;
  frequency_months?: number | null;
  last_completion_date?: string | null;
  valid_until?: string | null;
  extended_due_date?: string | null;
  days_until_due?: number | null;
  status: "OK" | "DUE_SOON" | "OVERDUE" | "DEFERRED" | "SCHEDULED_ONLY" | "NOT_DONE" | string;
  upcoming_event_id?: string | null;
  upcoming_event_date?: string | null;
  is_mandatory?: boolean;
  [key: string]: any;
}

export interface TrainingNotificationRead {
  id: string;
  amo_id: string;
  user_id: string;
  title?: string;
  body?: string;
  message?: string;
  severity: TrainingNotificationSeverity | string;
  link_path?: string | null;
  read_at?: string | null;
  created_at: string;
  [key: string]: any;
}

export interface TrainingNotificationMarkRead {
  notification_id?: string;
  read_at?: string;
}

export interface CourseImportSummary {
  created?: number;
  updated?: number;
  skipped?: number;
  errors?: string[];
  rows?: unknown[];
  [key: string]: any;
}

export interface TrainingRecordImportSummary extends CourseImportSummary {}

export interface TrainingAccessState {
  can_view?: boolean;
  can_edit?: boolean;
  can_verify?: boolean;
  can_import?: boolean;
  role?: string | null;
  portal_locked?: boolean;
  crs_blocked?: boolean;
  overdue_mandatory_count?: number;
  due_soon_mandatory_count?: number;
  deferred_mandatory_count?: number;
  upcoming_scheduled_count?: number;
  portal_lock_reason?: string | null;
  [key: string]: any;
}

export interface TrainingEventBatchScheduleCreate {
  course_id?: string;
  course_pk?: string;
  user_ids: string[];
  starts_on: string;
  ends_on?: string | null;
  title?: string | null;
  provider?: string | null;
  provider_kind?: string | null;
  delivery_mode?: string | null;
  venue_mode?: string | null;
  instructor_name?: string | null;
  location?: string | null;
  meeting_link?: string | null;
  notes?: string | null;
  participant_status?: TrainingParticipantStatus | string;
  auto_issue_certificates?: boolean;
  allow_self_attendance?: boolean;
  allow_online_overlap?: boolean;
  [key: string]: any;
}

export interface TrainingEventBatchScheduleRead {
  event: TrainingEventRead;
  participants: TrainingEventParticipantRead[];
  created_count?: number;
  [key: string]: any;
}

export interface TrainingAutoGroupScheduleCreate {
  course_id?: string;
  user_ids?: string[];
  base_start_on?: string | null;
  include_due_soon?: boolean;
  include_overdue?: boolean;
  include_not_done?: boolean;
  max_participants_per_session?: number;
  schedule_search_days?: number;
  avoid_weekends?: boolean;
  allow_online_overlap?: boolean;
  provider?: string | null;
  provider_kind?: string | null;
  delivery_mode?: string | null;
  venue_mode?: string | null;
  instructor_name?: string | null;
  location?: string | null;
  meeting_link?: string | null;
  notes?: string | null;
  participant_status?: TrainingParticipantStatus | string;
  auto_issue_certificates?: boolean;
  allow_self_attendance?: boolean;
  [key: string]: any;
}

export interface TrainingAutoGroupSkippedRead {
  user_id: string;
  course_pk?: string | null;
  course_code?: string | null;
  course_name?: string | null;
  reason: string;
  availability_status?: string | null;
  next_available_on?: string | null;
  [key: string]: any;
}

export interface TrainingAutoGroupedSessionRead {
  course_pk: string;
  course_code: string;
  course_name: string;
  availability_bucket: string;
  start_on: string;
  end_on?: string | null;
  event: TrainingEventRead;
  participants: TrainingEventParticipantRead[];
  [key: string]: any;
}

export interface TrainingAutoGroupScheduleRead {
  events?: TrainingEventRead[];
  participants?: TrainingEventParticipantRead[];
  sessions: TrainingAutoGroupedSessionRead[];
  skipped: TrainingAutoGroupSkippedRead[];
  total_sessions?: number;
  total_enrolled?: number;
  [key: string]: any;
}

export interface TrainingCertificateArtifactOptions {
  include_qr?: boolean;
  include_signature?: boolean;
  issue_certificate?: boolean;
  format?: "pdf" | "zip" | string;
  [key: string]: any;
}
