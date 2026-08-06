export const DATASET_ORDER = ["AU", "AI", "PM", "OOS", "RM", "SM", "STRUCTURES", "RECURRING", "ECTM"] as const;
export type WorkbookDatasetCode = (typeof DATASET_ORDER)[number];

export const WORKBOOK_PROFILES = [
  "SAFARILINK-C208B-RP",
  "SAFARILINK-DHC8-RP",
  "GENERIC-ANALYSIS-TEMPLATE",
] as const;

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

export type WorkbookField = FieldDefinition;
export type WorkbookFieldDefinition = DatasetDefinition;

export type WorkbookRecordCreate = {
  dataset_code: WorkbookDatasetCode;
  event_date: string;
  event_end_date?: string | null;
  aircraft_serial_number?: string | null;
  ata_chapter?: string | null;
  reference_code?: string | null;
  title: string;
  description?: string | null;
  payload: Record<string, unknown>;
  source_workbook?: string | null;
  source_sheet?: string | null;
  source_row_number?: number | null;
};

export type WorkbookRecord = WorkbookRecordCreate & {
  id: number;
  record_number: string;
  revision: number;
  status: WorkbookRecordStatus;
  derived_values: Record<string, unknown>;
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

export type StatisticalAlertRequest = {
  metric_code: string;
  metric_label: string;
  source_kind: "EVENT_COUNT" | "EVENT_RATE_PER_100_FH" | "DATASET_COUNT" | "DATASET_FIELD";
  period_start: string;
  period_end: string;
  bucket: "WEEK" | "MONTH";
  event_types: string[];
  dataset_code: WorkbookDatasetCode | null;
  metric_field: string | null;
  aircraft_serial_number: string | null;
  ata_chapter: string | null;
  warning_multiplier: number;
  alert_multiplier: number;
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
  series: Array<{ period: string; value?: number | null; numerator?: number; denominator?: number }>;
  generated_at: string;
};

export type MappingCreate = {
  profile_code: string;
  profile_name: string;
  workbook_family: string;
  dataset_code: WorkbookDatasetCode;
  source_sheet: string;
  source_column: string;
  canonical_field: string;
  data_type: string;
  required: boolean;
  unit: string | null;
  aliases: string[];
  transform: Record<string, unknown>;
};

export type MappingRow = MappingCreate & {
  id: number;
  active: boolean;
  created_at: string;
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

export type ContractCoverage = {
  mapped_fields: number;
  expected_fields: number;
  missing_fields: string[];
  missing_required_fields: string[];
  coverage_pct: number;
};

export type ParityContracts = {
  mapping: { profiles: Record<string, Record<WorkbookDatasetCode, ContractCoverage>>; datasets: Record<string, unknown> };
  report_layouts: {
    required_datasets: WorkbookDatasetCode[];
    layouts: Record<string, { datasets: WorkbookDatasetCode[]; missing_datasets: WorkbookDatasetCode[]; has_statistical_alerts: boolean }>;
  };
};

export type ReportSection = {
  code: string;
  title: string;
  kind: "SUMMARY" | "DATASET" | "EVENTS" | "STATISTICAL_ALERTS";
  dataset_code?: WorkbookDatasetCode;
  include?: boolean;
};

export type ReportLayoutCreate = {
  code: string;
  name: string;
  aircraft_family: string;
  sections: ReportSection[];
  page_settings: Record<string, unknown>;
};

export type ReportLayout = ReportLayoutCreate & {
  id: number;
  revision: number;
  active: boolean;
};

export type ReportRenderRequest = {
  layout_id: number;
  period_start: string;
  period_end: string;
  aircraft: string[];
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
