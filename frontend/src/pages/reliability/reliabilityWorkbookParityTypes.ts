export type WorkbookDatasetCode =
  | "AU"
  | "AI"
  | "PM"
  | "OOS"
  | "RM"
  | "SM"
  | "STRUCTURES"
  | "RECURRING"
  | "ECTM";

export type WorkbookRecordStatus = "DRAFT" | "APPROVED" | "CLOSED" | "REJECTED";
export type FieldDataType = "text" | "textarea" | "date" | "datetime" | "decimal" | "integer" | "boolean" | "select";

export type FieldDefinition = {
  key: string;
  label: string;
  data_type: FieldDataType;
  required: boolean;
  unit?: string | null;
  options: string[];
  help_text?: string | null;
};

export type DatasetDefinition = {
  code: WorkbookDatasetCode;
  name: string;
  workbook_sheet_names: string[];
  description: string;
  event_type?: string | null;
  fields: FieldDefinition[];
};

export type WorkbookRecord = {
  id: number;
  dataset_code: WorkbookDatasetCode;
  record_number: string;
  revision: number;
  status: WorkbookRecordStatus;
  event_date: string;
  event_end_date?: string | null;
  aircraft_serial_number?: string | null;
  ata_chapter?: string | null;
  reference_code?: string | null;
  title: string;
  description?: string | null;
  payload: Record<string, unknown>;
  derived_values: Record<string, unknown>;
  source_workbook?: string | null;
  source_sheet?: string | null;
  source_row_number?: number | null;
  canonical_event_id?: number | null;
  created_at: string;
  updated_at: string;
  approved_at?: string | null;
  closed_at?: string | null;
};

export type OosMetrics = {
  records: number;
  downtime_hours: number;
  scheduled_available_hours: number;
  available_hours: number;
  availability_pct?: number | null;
  mttr_hours?: number | null;
};

export type StatisticalAlert = {
  id: number;
  metric_code: string;
  metric_label: string;
  source_kind: string;
  dataset_code?: WorkbookDatasetCode | null;
  scope_type: string;
  scope_value?: string | null;
  period_start: string;
  period_end: string;
  bucket: "WEEK" | "MONTH";
  sample_size: number;
  mean: number;
  sample_stddev: number;
  warning_level: number;
  alert_level: number;
  formula: string;
  series: Array<{
    period: string;
    value?: number | null;
    numerator?: number;
    denominator?: number;
  }>;
  generated_at: string;
};

export type ParityRow = {
  dataset_code: WorkbookDatasetCode;
  dataset_name: string;
  required_fields: string[];
  optional_fields: string[];
  mapped_required_fields: string[];
  missing_required_fields: string[];
  coverage_pct: number;
  record_count: number;
};

export type MappingSeedResult = {
  profiles: string[];
  expected_rows: number;
  created: number;
  repaired: number;
  total_active: number;
};

export type ReportLayout = {
  id: number;
  code: string;
  name: string;
  aircraft_family: string;
  revision: number;
  active: boolean;
  sections: Array<Record<string, unknown>>;
  page_settings: Record<string, unknown>;
};

export type ReportSnapshot = {
  id: number;
  layout_id: number;
  layout_code: string;
  layout_name?: string;
  period_start: string;
  period_end: string;
  aircraft: string[];
  sha256_hash: string;
  generated_at: string;
  download_url: string;
};

export type WorkspaceSection = "registers" | "alerts" | "mapping" | "reports";
