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
  elapsed_ms?: number | null;
}

export type QmsOperationalTone = "danger" | "warning" | "neutral" | "positive";
export type QmsKpiDirection = "improving" | "deteriorating" | "flat" | "not_available";

export interface QmsOperationalActionItem {
  id: string;
  label: string;
  count: number;
  oldest_age_days?: number | null;
  owner_status?: string | null;
  next_action: string;
  route: string;
  tone: QmsOperationalTone;
  priority: number;
  regulatory_consequence?: string | null;
}

export interface QmsOperationalWorkItem {
  id: string;
  title: string;
  severity?: string | null;
  created_at?: string | null;
  route: string;
}

export interface QmsOperationalObligation {
  id: string;
  module?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  title: string;
  date: string | null;
  event_type?: string | null;
  link?: string | null;
  due_state?: string | null;
  actionable?: boolean | null;
  subtitle?: string | null;
}

export interface QmsOperationalKpi {
  id: string;
  label: string;
  current: number | null;
  target: number | null;
  previous: number | null;
  direction: QmsKpiDirection;
  unit: string;
  route: string;
  data_status: "available" | "not_available";
}

export interface QmsOperationalSourceHealth {
  status: "healthy" | "partial" | "unavailable";
  error_count: number;
  errors_by_source?: Record<string, number>;
  errors?: QmsSourceError[];
}

export interface QmsOperationalDashboardResponse {
  contract: "qms-operational-dashboard.v2";
  tenant?: {
    amo_code: string;
    amo_id?: string;
  };
  as_of: string;
  action_queue: QmsOperationalActionItem[];
  my_work: QmsOperationalWorkItem[];
  upcoming_obligations: QmsOperationalObligation[];
  performance_kpis: QmsOperationalKpi[];
  aging_buckets?: Record<string, Record<string, number>>;
  unassigned_counts?: Record<string, number | null>;
  severity_breakdown?: Record<string, Record<string, number>>;
  period_comparisons?: {
    status?: string;
    note?: string;
  };
  data_freshness?: {
    generated_at?: string;
    counter_source?: string;
    counter_as_of?: string;
    calendar_start?: string;
    calendar_end?: string;
  };
  source_health: QmsOperationalSourceHealth;
  counters: QmsCounterMap;
  trace_id?: string | null;
  elapsed_ms?: number | null;
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
  source_errors?: QmsSourceError[];
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
