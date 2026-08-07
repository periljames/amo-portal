export const DATASET_ORDER = ["AU", "AI", "FI", "PM", "OOS", "RM", "SM", "SR", "SB", "CS", "AS", "UR", "STRUCTURES", "RECURRING", "ECTM", "ADD"] as const;
export type WorkbookDatasetCode = (typeof DATASET_ORDER)[number];

export const WORKBOOK_PROFILES = [
  "SAFARILINK-C208B-RP",
  "SAFARILINK-DHC8-RP",
  "GENERIC-ANALYSIS-TEMPLATE",
] as const;

export type WorkbookRecordStatus = "DRAFT" | "APPROVED" | "CLOSED" | "REJECTED";
export type FieldDataType = "text" | "textarea" | "date" | "datetime" | "decimal" | "integer" | "boolean" | "select";

export type FieldDefinition = { key: string; label: string; data_type: FieldDataType; required: boolean; unit?: string | null; options: string[]; help_text?: string | null };
export type DatasetDefinition = { code: WorkbookDatasetCode; name: string; workbook_sheet_names: string[]; description: string; event_type?: string | null; fields: FieldDefinition[] };
export type WorkbookField = FieldDefinition;
export type WorkbookFieldDefinition = DatasetDefinition;

export type WorkbookRecordCreate = {
  dataset_code: WorkbookDatasetCode; event_date: string; event_end_date?: string | null; aircraft_serial_number?: string | null;
  ata_chapter?: string | null; reference_code?: string | null; title: string; description?: string | null; payload: Record<string, unknown>;
  source_workbook?: string | null; source_sheet?: string | null; source_row_number?: number | null;
};
export type WorkbookRecord = WorkbookRecordCreate & { id: number; record_number: string; revision: number; status: WorkbookRecordStatus; derived_values: Record<string, unknown>; canonical_event_id?: number | null; created_at: string; updated_at: string; approved_at?: string | null; closed_at?: string | null };
export type OosMetrics = { records: number; downtime_hours: number; scheduled_available_hours: number; available_hours: number; availability_pct?: number | null; mttr_hours?: number | null };

export type StatisticalMethod = "SAMPLE_SIGMA" | "WORKBOOK_COMPATIBLE" | "POISSON_U_CHART";
export type StatisticalAlertRequest = {
  metric_code: string; metric_label: string;
  source_kind: "EVENT_COUNT" | "EVENT_RATE" | "EVENT_RATE_PER_100_FH" | "DATASET_COUNT" | "DATASET_FIELD";
  period_start: string; period_end: string; bucket: "WEEK" | "MONTH"; event_types: string[];
  dataset_code: WorkbookDatasetCode | null; metric_field: string | null; aircraft_serial_number: string | null; ata_chapter: string | null;
  method: StatisticalMethod; denominator_kind: "FLIGHT_HOURS" | "FLIGHT_CYCLES"; rate_scale: number; baseline_periods: number;
  warning_multiplier: number; alert_multiplier: number;
};
export type StatisticalSeriesPoint = {
  period: string; value?: number | null; exact_value?: string | null; numerator?: number; exact_numerator?: string | null;
  denominator?: number; exact_denominator?: string | null; denominator_kind?: string; rate_scale?: string; observations?: number;
  exposure_rows?: number; quality?: string; warning_level?: number | null; alert_level?: number | null;
  exact_warning_level?: string | null; exact_alert_level?: string | null;
};
export type StatisticalAlert = {
  id: number; metric_code: string; metric_label: string; source_kind: string; dataset_code?: WorkbookDatasetCode | null;
  scope_type: string; scope_value?: string | null; period_start: string; period_end: string; bucket: "WEEK" | "MONTH";
  method?: StatisticalMethod; denominator_kind?: string; rate_scale?: string; sample_size: number; mean: number; exact_mean?: string;
  sample_stddev: number; exact_sample_stddev?: string; warning_level: number; exact_warning_level?: string; alert_level: number;
  exact_alert_level?: string; moving_mean_stddev?: string | null; formula: string; formula_snapshot_hash?: string;
  data_completeness?: { periods: number; valid_periods: number; withheld_periods: number }; series: StatisticalSeriesPoint[]; generated_at: string;
};

export type MappingCreate = { profile_code: string; profile_name: string; workbook_family: string; dataset_code: WorkbookDatasetCode; source_sheet: string; source_column: string; canonical_field: string; data_type: string; required: boolean; unit: string | null; aliases: string[]; transform: Record<string, unknown> };
export type MappingRow = MappingCreate & { id: number; active: boolean; created_at: string };
export type ParityRow = { dataset_code: WorkbookDatasetCode; dataset_name: string; required_fields: string[]; optional_fields: string[]; mapped_required_fields: string[]; missing_required_fields: string[]; coverage_pct: number; record_count: number };
export type MappingSeedResult = { profiles: string[]; expected_rows: number; created: number; repaired: number; total_active: number };
export type ContractCoverage = { mapped_fields: number; expected_fields: number; missing_fields: string[]; missing_required_fields: string[]; coverage_pct: number };
export type ParityContracts = { mapping: { profiles: Record<string, Record<WorkbookDatasetCode, ContractCoverage>>; datasets: Record<string, unknown> }; report_layouts: { required_datasets: WorkbookDatasetCode[]; layouts: Record<string, { datasets: WorkbookDatasetCode[]; missing_datasets: WorkbookDatasetCode[]; has_statistical_alerts: boolean }> } };

export type ReportSection = { code: string; title: string; kind: "SUMMARY" | "DATASET" | "EVENTS" | "STATISTICAL_ALERTS"; dataset_code?: WorkbookDatasetCode; include?: boolean };
export type ReportLayoutCreate = { code: string; name: string; aircraft_family: string; sections: ReportSection[]; page_settings: Record<string, unknown> };
export type ReportLayout = ReportLayoutCreate & { id: number; revision: number; active: boolean };
export type ReportRenderRequest = { layout_id: number; period_start: string; period_end: string; aircraft: string[] };
export type ReportSnapshot = { id: number; layout_id: number; layout_code: string; layout_name?: string; period_start: string; period_end: string; aircraft: string[]; sha256_hash: string; generated_at: string; download_url: string };

export type WorkbookIntegrity = {
  has_vba?: boolean; has_vba_signature?: boolean; external_link_count?: number; chart_count?: number; formula_count?: number;
  formula_error_counts?: Record<string, number>; hidden_sheet_count?: number; protected_sheet_count?: number; broken_defined_names?: string[];
  source_hash?: string; structural_fingerprint?: string; profile_match?: { matched: boolean; missing_sheets?: string[]; unexpected_sheets?: string[] };
  vba_execution?: string; external_links?: string; formula_policy?: string; selected_sheet?: string; selected_sheet_state?: string;
};
export type WorkbookImportStatus = "PREVIEW_READY" | "PROCESSING" | "COMPLETED" | "PARTIAL_FAILED" | "FAILED";
export type WorkbookImportRowStatus = "VALID" | "INVALID" | "COMMITTED" | "FAILED";
export type WorkbookImportSheet = { name: string; state: string; max_row: number; max_column: number; integrity?: WorkbookIntegrity };
export type WorkbookImportBatch = {
  id: number; profile_code: string; dataset_code: WorkbookDatasetCode; original_filename: string; sanitized_filename: string; file_extension: string;
  file_size_bytes: number; source_hash: string; status: WorkbookImportStatus; detected_sheets: WorkbookImportSheet[]; selected_sheet: string;
  header_row: number; header_map: Record<string, string>; total_rows: number; valid_rows: number; invalid_rows: number; committed_rows: number;
  failed_rows: number; created_at: string; updated_at: string; completed_at?: string | null; integrity?: WorkbookIntegrity | null;
};
export type WorkbookImportRow = { id: number; row_number: number; status: WorkbookImportRowStatus; raw_values: Record<string, unknown>; mapped_values: Record<string, unknown>; errors: string[]; row_source_hash: string; attempt_count?: number; last_error?: string | null; workbook_record_id?: number | null };
export type WorkbookImportPreview = WorkbookImportBatch & { preview_rows: WorkbookImportRow[]; preview_truncated: boolean };
export type WorkbookImportList = { total: number; offset: number; limit: number; items: WorkbookImportBatch[] };
export type WorkbookImportDetail = WorkbookImportBatch & { row_total: number; row_offset: number; row_limit: number; rows: WorkbookImportRow[] };
export type WorkbookImportCommitResult = WorkbookImportBatch & { processed: number; remaining_valid_rows?: number; reset_rows?: number; message?: string };
export type WorkspaceSection = "registers" | "alerts" | "mapping" | "reports";
