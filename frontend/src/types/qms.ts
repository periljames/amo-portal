// src/types/qms.ts
export type QmsModuleKey =
  | "cockpit"
  | "inbox"
  | "calendar"
  | "system"
  | "documents"
  | "audits"
  | "findings"
  | "cars"
  | "risk"
  | "change-control"
  | "training-competence"
  | "suppliers"
  | "equipment-calibration"
  | "external-interface"
  | "management-review"
  | "reports"
  | "evidence-vault"
  | "settings";

export type QmsCounterMap = Record<string, number>;

export interface QmsSourceError {
  label: string;
  message: string;
  type?: string;
  trace_id?: string;
}


export interface QmsDashboardResponse {
  tenant?: {
    amo_code: string;
    amo_id?: string;
  };
  source?: string;
  as_of?: string;
  counters: QmsCounterMap;
  links?: Record<string, string>;
  source_errors?: QmsSourceError[];
  warning?: string | null;
  trace_id?: string | null;
}

export interface QmsListResponse<T = Record<string, unknown>> {
  items?: T[];
  status?: string;
  message?: string;
}

export interface QmsInboxResponse extends QmsListResponse {
  items?: Array<{
    id: string;
    message: string;
    severity?: string | null;
    created_at?: string | null;
    read_at?: string | null;
  }>;
}

export interface QmsCalendarResponse extends QmsListResponse {
  start?: string;
  end?: string;
  integration_contract?: string;
  source_count?: number;
  returned_count?: number;
  limit?: number;
  offset?: number;
  items?: Array<{
    id: string;
    module: string;
    entity_type: string;
    entity_id: string;
    title: string;
    date: string | null;
    event_type: string;
    link?: string | null;
    personnel_name?: string | null;
    course_name?: string | null;
    due_state?: string | null;
    audit_ref?: string | null;
    kind?: string | null;
    status?: string | null;
    planned_start?: string | null;
    planned_end?: string | null;
    auditee?: string | null;
    auditee_email?: string | null;
    lead_auditor_user_id?: string | null;
    frequency?: string | null;
    calendar_group?: string | null;
    source_origin?: string | null;
    subtitle?: string | null;
    actionable?: boolean | null;
  }>;
}

export interface QmsTrainingDashboardResponse {
  total_records: number;
  expired_records: number;
  expiring_records: number;
}
