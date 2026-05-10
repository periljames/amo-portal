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

export interface QmsDashboardResponse {
  tenant?: {
    amo_code: string;
    amo_id?: string;
  };
  source?: string;
  as_of?: string;
  counters: QmsCounterMap;
  links?: Record<string, string>;
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
  items?: Array<{
    id: string;
    module: string;
    entity_type: string;
    entity_id: string;
    title: string;
    date: string | null;
    event_type: string;
    link?: string | null;
  }>;
}

export interface QmsTrainingDashboardResponse {
  total_records: number;
  expired_records: number;
  expiring_records: number;
}
