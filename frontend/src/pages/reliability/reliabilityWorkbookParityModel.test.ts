import { describe, expect, it } from "vitest";
import { spreadsheetSafeText } from "./ReliabilityWorkbenchUtils";
import { activeReportSections, buildRecordCreate, defaultReportSections, initialCommonDraft, initialPayload, moveSection, validateRecordDraft, workbookRecordsCsv } from "./reliabilityWorkbookParityModel";
import type { WorkbookFieldDefinition, WorkbookRecord } from "./reliabilityWorkbookParityTypes";

const AU: WorkbookFieldDefinition = { code: "AU", name: "Aircraft utilisation", workbook_sheet_names: ["AU"], description: "Controlled denominator evidence", fields: [
  { key: "flight_hours", label: "Flight hours", data_type: "decimal", required: true, unit: "FH", options: [] },
  { key: "flight_cycles", label: "Flight cycles", data_type: "integer", required: true, unit: "FC", options: [] },
  { key: "confirmed", label: "Confirmed", data_type: "boolean", required: false, options: [] },
] };

describe("Reliability workbook parity model", () => {
  it("builds typed controlled records without floating point conversion", () => { const common = { ...initialCommonDraft(AU), eventDate: "2026-08-01", aircraft: "5Y-SLK", title: "Daily utilisation" }; const payload = { ...initialPayload(AU), flight_hours: "12.75", flight_cycles: "8", confirmed: true }; const record = buildRecordCreate(AU, common, payload); expect(record.dataset_code).toBe("AU"); expect(record.payload.flight_hours).toBe("12.75"); expect(record.payload.flight_cycles).toBe(8); expect(record.payload.confirmed).toBe(true); });
  it("enforces required workbook fields and date order", () => { const common = { ...initialCommonDraft(AU), eventDate: "2026-08-02", eventEndDate: "2026-08-01", title: "" }; const errors = validateRecordDraft(AU, common, initialPayload(AU)); expect(errors).toContain("Record title is required."); expect(errors).toContain("Event end date cannot precede the event date."); expect(errors).toContain("Flight hours is required."); expect(errors).toContain("Flight cycles is required."); });
  it("keeps all controlled workbook and analytical domains in report layouts", () => { const sections = activeReportSections(defaultReportSections()); const datasets = sections.flatMap((section) => section.dataset_code ? [section.dataset_code] : []); expect(new Set(datasets).size).toBe(16); expect(datasets).toEqual(expect.arrayContaining(["FI", "SR", "SB", "CS", "AS", "UR", "ADD"])); expect(sections.some((section) => section.kind === "STATISTICAL_ALERTS")).toBe(true); expect(moveSection(sections, 1, 1)[2].code).toBe("AU"); });
  it("exports the loaded controlled register using canonical columns", () => { const record: WorkbookRecord = { ...buildRecordCreate(AU, { ...initialCommonDraft(AU), eventDate: "2026-08-01", title: "Daily utilisation" }, { flight_hours: "4.25", flight_cycles: "3", confirmed: true }), id: 1, record_number: "AU-2026-0001", revision: 1, status: "APPROVED", derived_values: {}, created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-01T00:00:00Z" }; const csv = workbookRecordsCsv([record], AU); expect(csv).toContain("flight_hours"); expect(csv).toContain("4.25"); expect(csv).toContain("AU-2026-0001"); });
  it("neutralizes spreadsheet formulas before workbench clipboard or CSV export", () => { expect(spreadsheetSafeText("=HYPERLINK(\"https://example.invalid\")")).toBe("'=HYPERLINK(\"https://example.invalid\")"); expect(spreadsheetSafeText("+SUM(A1:A2)")).toBe("'+SUM(A1:A2)"); expect(spreadsheetSafeText("@cmd")).toBe("'@cmd"); expect(spreadsheetSafeText("5Y-SLK")).toBe("5Y-SLK"); });
});
