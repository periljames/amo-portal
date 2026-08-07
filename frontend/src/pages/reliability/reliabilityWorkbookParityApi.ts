import { apiRequest } from "../../services/apiClient";
import type {
  MappingCreate,
  MappingRow,
  MappingSeedResult,
  OosMetrics,
  ParityContracts,
  ParityRow,
  ReportLayout,
  ReportLayoutCreate,
  ReportRenderRequest,
  ReportSnapshot,
  StatisticalAlert,
  StatisticalAlertRequest,
  WorkbookDatasetCode,
  WorkbookFieldDefinition,
  WorkbookImportCommitResult,
  WorkbookImportDetail,
  WorkbookImportList,
  WorkbookImportPreview,
  WorkbookRecord,
  WorkbookRecordCreate,
  WorkbookRecordStatus,
} from "./reliabilityWorkbookParityTypes";

const ROOT = "/reliability/workbook-parity";

function queryString(values: Record<string, string | number | undefined | null>): string {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== "") params.set(key, String(value));
  });
  const output = params.toString();
  return output ? `?${output}` : "";
}

export type RecordListFilters = {
  datasetCode?: WorkbookDatasetCode;
  aircraft?: string;
  status?: WorkbookRecordStatus | "";
  periodStart?: string;
  periodEnd?: string;
  q?: string;
  limit?: number;
  offset?: number;
};

export async function listWorkbookCatalog(): Promise<WorkbookFieldDefinition[]> {
  return apiRequest<WorkbookFieldDefinition[]>(`${ROOT}/catalog`, { cacheTtlMs: 60_000 });
}

export async function listWorkbookRecords(filters: RecordListFilters): Promise<WorkbookRecord[]> {
  return apiRequest<WorkbookRecord[]>(`${ROOT}/records${queryString({
    dataset_code: filters.datasetCode,
    aircraft_serial_number: filters.aircraft,
    status: filters.status,
    period_start: filters.periodStart,
    period_end: filters.periodEnd,
    q: filters.q,
    limit: filters.limit ?? 50,
    offset: filters.offset ?? 0,
  })}`, { cacheTtlMs: 0 });
}

export async function createWorkbookRecord(payload: WorkbookRecordCreate): Promise<WorkbookRecord> {
  return apiRequest<WorkbookRecord>(`${ROOT}/records`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function transitionWorkbookRecord(
  recordId: number,
  action: "approve" | "close",
  note: string,
): Promise<WorkbookRecord> {
  return apiRequest<WorkbookRecord>(`${ROOT}/records/${recordId}/${action}`, {
    method: "POST",
    body: JSON.stringify({ note }),
  });
}

export async function getOosMetrics(filters: {
  periodStart: string;
  periodEnd: string;
  aircraft?: string;
}): Promise<OosMetrics> {
  return apiRequest<OosMetrics>(`${ROOT}/oos-metrics${queryString({
    period_start: filters.periodStart,
    period_end: filters.periodEnd,
    aircraft_serial_number: filters.aircraft,
  })}`, { cacheTtlMs: 0 });
}

export async function calculateStatisticalAlert(payload: StatisticalAlertRequest): Promise<StatisticalAlert> {
  return apiRequest<StatisticalAlert>(`${ROOT}/statistical-alerts/calculate`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listStatisticalAlerts(limit = 100): Promise<StatisticalAlert[]> {
  return apiRequest<StatisticalAlert[]>(`${ROOT}/statistical-alerts?limit=${limit}`, { cacheTtlMs: 0 });
}

export async function seedDefaultMappings(): Promise<MappingSeedResult> {
  return apiRequest<MappingSeedResult>(`${ROOT}/mappings/seed-defaults`, { method: "POST" });
}

export async function listMappings(profileCode?: string): Promise<MappingRow[]> {
  return apiRequest<MappingRow[]>(`${ROOT}/mappings${queryString({ profile_code: profileCode })}`, { cacheTtlMs: 0 });
}

export async function createMapping(payload: MappingCreate): Promise<MappingRow> {
  return apiRequest<MappingRow>(`${ROOT}/mappings`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function readMappingParity(): Promise<ParityRow[]> {
  return apiRequest<ParityRow[]>(`${ROOT}/parity`, { cacheTtlMs: 0 });
}

export async function readParityContracts(): Promise<ParityContracts> {
  return apiRequest<ParityContracts>(`${ROOT}/contracts`, { cacheTtlMs: 0 });
}

export async function previewWorkbookImport(input: {
  file: File;
  profileCode: string;
  datasetCode: WorkbookDatasetCode;
  sourceSheet?: string;
  headerRow?: number;
}): Promise<WorkbookImportPreview> {
  const body = new FormData();
  body.set("profile_code", input.profileCode);
  body.set("dataset_code", input.datasetCode);
  body.set("header_row", String(input.headerRow ?? 1));
  if (input.sourceSheet?.trim()) body.set("source_sheet", input.sourceSheet.trim());
  body.set("workbook", input.file, input.file.name);
  return apiRequest<WorkbookImportPreview>(`${ROOT}/imports/preview`, {
    method: "POST",
    body,
    timeoutMs: 120_000,
  });
}

export async function listWorkbookImports(filters: {
  status?: string;
  profileCode?: string;
  datasetCode?: WorkbookDatasetCode;
  limit?: number;
  offset?: number;
} = {}): Promise<WorkbookImportList> {
  return apiRequest<WorkbookImportList>(`${ROOT}/imports${queryString({
    status: filters.status,
    profile_code: filters.profileCode,
    dataset_code: filters.datasetCode,
    limit: filters.limit ?? 50,
    offset: filters.offset ?? 0,
  })}`, { cacheTtlMs: 0 });
}

export async function readWorkbookImport(
  batchId: number,
  filters: { rowStatus?: string; limit?: number; offset?: number } = {},
): Promise<WorkbookImportDetail> {
  return apiRequest<WorkbookImportDetail>(`${ROOT}/imports/${batchId}${queryString({
    row_status: filters.rowStatus,
    limit: filters.limit ?? 200,
    offset: filters.offset ?? 0,
  })}`, { cacheTtlMs: 0 });
}

export async function commitWorkbookImport(batchId: number, chunkSize = 100): Promise<WorkbookImportCommitResult> {
  return apiRequest<WorkbookImportCommitResult>(`${ROOT}/imports/${batchId}/commit`, {
    method: "POST",
    body: JSON.stringify({ chunk_size: chunkSize }),
    timeoutMs: 120_000,
  });
}

export async function retryWorkbookImport(batchId: number): Promise<WorkbookImportCommitResult> {
  return apiRequest<WorkbookImportCommitResult>(`${ROOT}/imports/${batchId}/retry`, {
    method: "POST",
    body: JSON.stringify({ failed_only: true }),
  });
}

export async function seedDefaultReportLayouts(): Promise<ReportLayout[]> {
  return apiRequest<ReportLayout[]>(`${ROOT}/report-layouts/seed`, { method: "POST" });
}

export async function listReportLayouts(): Promise<ReportLayout[]> {
  return apiRequest<ReportLayout[]>(`${ROOT}/report-layouts`, { cacheTtlMs: 0 });
}

export async function createReportLayout(payload: ReportLayoutCreate): Promise<ReportLayout> {
  return apiRequest<ReportLayout>(`${ROOT}/report-layouts`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function renderWorkbookReport(payload: ReportRenderRequest): Promise<ReportSnapshot> {
  return apiRequest<ReportSnapshot>(`${ROOT}/reports/render`, {
    method: "POST",
    body: JSON.stringify(payload),
    timeoutMs: 120_000,
  });
}

export async function listReportSnapshots(limit = 100): Promise<ReportSnapshot[]> {
  return apiRequest<ReportSnapshot[]>(`${ROOT}/reports?limit=${limit}`, { cacheTtlMs: 0 });
}

export async function readReportHtml(snapshotId: number): Promise<string> {
  return apiRequest<string>(`${ROOT}/reports/${snapshotId}/html`, {
    headers: { Accept: "text/html" },
    cacheTtlMs: 0,
  });
}
