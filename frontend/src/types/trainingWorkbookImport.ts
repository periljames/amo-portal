export type TrainingWorkbookImportStatus =
  | "QUEUED"
  | "PARSING"
  | "PREVIEW_READY"
  | "REVIEW_REQUIRED"
  | "QUEUED_COMMIT"
  | "COMMITTING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export interface TrainingWorkbookImportSheet {
  id: string;
  sheet_name: string;
  visibility: string;
  classification: string;
  portal_destination: string;
  is_operational: boolean;
  display_order: number;
  status: string;
  total_rows: number;
  processed_rows: number;
  created_count: number;
  updated_count: number;
  unchanged_count: number;
  skipped_count: number;
  failed_count: number;
  review_count: number;
  message?: string | null;
}

export interface TrainingWorkbookImportRow {
  id: string;
  sheet_name: string;
  source_row: number;
  entity_type: string;
  source_key?: string | null;
  display_label?: string | null;
  proposed_action: string;
  status: string;
  decision_required: boolean;
  decision?: string | null;
  decision_options: string[];
  changes: Array<{ field?: string; old?: unknown; new?: unknown; [key: string]: unknown }>;
  issue_code?: string | null;
  issue_message?: string | null;
  payload: Record<string, unknown>;
  committed_entity_id?: string | null;
}

export interface TrainingWorkbookImportRowPage {
  total: number;
  limit: number;
  offset: number;
  items: TrainingWorkbookImportRow[];
}

export interface TrainingWorkbookImportJob {
  id: string;
  amo_id: string;
  actor_user_id?: string | null;
  filename: string;
  size_bytes: number;
  file_sha256: string;
  duplicate_of_job_id?: string | null;
  status: TrainingWorkbookImportStatus | string;
  stage: string;
  current_sheet?: string | null;
  current_record_label?: string | null;
  processed_rows: number;
  total_rows: number;
  created_count: number;
  updated_count: number;
  unchanged_count: number;
  skipped_count: number;
  failed_count: number;
  review_count: number;
  summary: Record<string, unknown>;
  error_message?: string | null;
  cancel_requested: boolean;
  created_at: string;
  started_at?: string | null;
  preview_completed_at?: string | null;
  committed_at?: string | null;
  completed_at?: string | null;
  updated_at: string;
  sheets: TrainingWorkbookImportSheet[];
}

export interface TrainingWorkbookImportJobPage {
  items: TrainingWorkbookImportJob[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface TrainingWorkbookImportDecision {
  row_id: string;
  decision: string;
}

export interface PersonnelLicenceRead {
  id: string;
  personnel_profile_id: string;
  user_id?: string | null;
  authority: string;
  country?: string | null;
  licence_number: string;
  category_code?: string | null;
  category_source?: string | null;
  issued_on?: string | null;
  expires_on?: string | null;
  expiry_source_record_id?: string | null;
  expiry_source_course_id?: string | null;
  expiry_synced_at?: string | null;
  internal_stamp_no?: string | null;
  initial_authorization_date?: string | null;
  status: string;
  is_primary: boolean;
  created_at: string;
  updated_at: string;
}

export interface TrainingRoleGroupRead {
  id: string;
  code: string;
  description?: string | null;
  is_active: boolean;
}

export interface TrainingPersonRoleRead {
  id: string;
  person_id: string;
  personnel_profile_id?: string | null;
  user_id?: string | null;
  role_group_id: string;
  role_group_code?: string | null;
  person_name?: string | null;
  staff_code?: string | null;
  department?: string | null;
  position?: string | null;
  notes?: string | null;
  is_active: boolean;
}

export interface TrainingCourseRoleRuleRead {
  id: string;
  course_id: string;
  course_code?: string | null;
  course_name?: string | null;
  role_group_id: string;
  role_group_code?: string | null;
  is_required: boolean;
  requirement_type: string;
  notes?: string | null;
  is_active: boolean;
}
