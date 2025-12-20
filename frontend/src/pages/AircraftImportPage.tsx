// frontend/src/pages/AircraftImportPage.tsx
import React, { useEffect, useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

type AircraftRowData = {
  serial_number: string;
  registration: string;
  template?: string | null;
  make?: string | null;
  model?: string | null;
  home_base?: string | null;
  owner?: string | null;
  aircraft_model_code?: string | null;
  operator_code?: string | null;
  supplier_code?: string | null;
  company_name?: string | null;
  internal_aircraft_identifier?: string | null;
  status?: string | null;
  is_active?: boolean | null;
  last_log_date?: string | null;
  total_hours?: number | string | null;
  total_cycles?: number | string | null;
};

type PreviewRow = {
  row_number: number;
  data: AircraftRowData;
  errors: string[];
  warnings: string[];
  action: "new" | "update" | "invalid";
  approved: boolean;
  suggested_template?: SuggestedTemplate | null;
};

type SuggestedTemplate = {
  id: number;
  name: string;
  aircraft_template?: string | null;
  model_code?: string | null;
  operator_code?: string | null;
};

type AircraftImportTemplate = {
  id: number;
  name: string;
  template_type?: string | null;
  aircraft_template?: string | null;
  model_code?: string | null;
  operator_code?: string | null;
  column_mapping?: Record<string, string | null> | null;
  default_values?: Record<string, any> | null;
};

type OcrPreview = {
  confidence?: number | null;
  samples?: string[];
  text?: string | null;
  file_type?: string | null;
};

type ComponentRowData = {
  position: string;
  ata?: string | null;
  part_number?: string | null;
  serial_number?: string | null;
  description?: string | null;
  installed_date?: string | null;
  installed_hours?: number | string | null;
  installed_cycles?: number | string | null;
  current_hours?: number | string | null;
  current_cycles?: number | string | null;
  notes?: string | null;
  manufacturer_code?: string | null;
  operator_code?: string | null;
};

type ComponentPreviewRow = {
  row_number: number;
  data: ComponentRowData;
  errors: string[];
  warnings: string[];
  action: "new" | "update" | "invalid";
  approved: boolean;
  existing_component?: {
    position?: string | null;
    part_number?: string | null;
    serial_number?: string | null;
  } | null;
  dedupe_suggestions?: {
    source: "file" | "existing";
    part_number: string;
    serial_number: string;
    positions: string[];
  }[];
};

const AircraftImportPage: React.FC = () => {
  const [aircraftFile, setAircraftFile] = useState<File | null>(null);
  const [componentsFile, setComponentsFile] = useState<File | null>(null);
  const [componentAircraftSerial, setComponentAircraftSerial] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [previewRows, setPreviewRows] = useState<PreviewRow[]>([]);
  const [columnMapping, setColumnMapping] = useState<
    Record<string, string | null> | null
  >(null);
  const [ocrPreview, setOcrPreview] = useState<OcrPreview | null>(null);
  const [ocrTextDraft, setOcrTextDraft] = useState("");
  const [previewSummary, setPreviewSummary] = useState<{
    new: number;
    update: number;
    invalid: number;
  } | null>(null);
  const [templates, setTemplates] = useState<AircraftImportTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | "">("");
  const [templateName, setTemplateName] = useState("");
  const [templateAircraftTemplate, setTemplateAircraftTemplate] = useState("");
  const [templateModelCode, setTemplateModelCode] = useState("");
  const [templateOperatorCode, setTemplateOperatorCode] = useState("");
  const [templateDefaultsJson, setTemplateDefaultsJson] = useState("{}");
  const [templateLoading, setTemplateLoading] = useState(false);
  const [componentPreviewLoading, setComponentPreviewLoading] = useState(false);
  const [componentConfirmLoading, setComponentConfirmLoading] = useState(false);
  const [componentPreviewRows, setComponentPreviewRows] = useState<
    ComponentPreviewRow[]
  >([]);
  const [componentColumnMapping, setComponentColumnMapping] = useState<
    Record<string, string | null> | null
  >(null);
  const [componentSummary, setComponentSummary] = useState<{
    new: number;
    update: number;
    invalid: number;
  } | null>(null);
  const [componentTemplates, setComponentTemplates] = useState<
    AircraftImportTemplate[]
  >([]);
  const [componentSelectedTemplateId, setComponentSelectedTemplateId] =
    useState<number | "">("");
  const [componentTemplateName, setComponentTemplateName] = useState("");
  const [componentTemplateAircraftTemplate, setComponentTemplateAircraftTemplate] =
    useState("");
  const [componentTemplateModelCode, setComponentTemplateModelCode] =
    useState("");
  const [componentTemplateOperatorCode, setComponentTemplateOperatorCode] =
    useState("");
  const [componentTemplateDefaultsJson, setComponentTemplateDefaultsJson] =
    useState("{}");
  const [componentTemplateLoading, setComponentTemplateLoading] =
    useState(false);

  const handleAircraftFileChange = (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    setAircraftFile(e.target.files?.[0] ?? null);
  };

  const handleComponentsFileChange = (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    setComponentsFile(e.target.files?.[0] ?? null);
  };

  const validateRow = (data: AircraftRowData) => {
    const errors: string[] = [];
    if (!data.serial_number?.trim() && !data.registration?.trim()) {
      errors.push("Missing serial and registration.");
    } else if (!data.serial_number?.trim()) {
      errors.push("Missing serial number.");
    } else if (!data.registration?.trim()) {
      errors.push("Missing registration.");
    }
    return errors;
  };

  const hasErrors = (row: PreviewRow) => row.errors.length > 0;

  const validateComponentRow = (data: ComponentRowData) => {
    const errors: string[] = [];
    if (!data.position?.trim()) {
      errors.push("Missing component position.");
    }
    return errors;
  };

  const hasComponentErrors = (row: ComponentPreviewRow) =>
    row.errors.length > 0;

  const loadTemplates = async () => {
    try {
      const res = await fetch(
        `${API_BASE}/aircraft/import/templates?template_type=aircraft`
      );
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail ?? "Failed to load templates.");
      }
      setTemplates(data ?? []);
    } catch (err: any) {
      setMessage(err.message ?? "Error loading templates.");
    }
  };

  const loadComponentTemplates = async () => {
    try {
      const res = await fetch(
        `${API_BASE}/aircraft/import/templates?template_type=components`
      );
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail ?? "Failed to load component templates.");
      }
      setComponentTemplates(data ?? []);
    } catch (err: any) {
      setMessage(err.message ?? "Error loading component templates.");
    }
  };

  useEffect(() => {
    void loadTemplates();
    void loadComponentTemplates();
  }, []);

  useEffect(() => {
    if (selectedTemplateId === "") {
      setTemplateName("");
      setTemplateAircraftTemplate("");
      setTemplateModelCode("");
      setTemplateOperatorCode("");
      setTemplateDefaultsJson("{}");
      return;
    }
    const selected = templates.find(
      (template) => template.id === selectedTemplateId
    );
    if (!selected) {
      return;
    }
    setTemplateName(selected.name ?? "");
    setTemplateAircraftTemplate(selected.aircraft_template ?? "");
    setTemplateModelCode(selected.model_code ?? "");
    setTemplateOperatorCode(selected.operator_code ?? "");
    setTemplateDefaultsJson(
      JSON.stringify(selected.default_values ?? {}, null, 2)
    );
  }, [selectedTemplateId, templates]);

  useEffect(() => {
    if (componentSelectedTemplateId === "") {
      setComponentTemplateName("");
      setComponentTemplateAircraftTemplate("");
      setComponentTemplateModelCode("");
      setComponentTemplateOperatorCode("");
      setComponentTemplateDefaultsJson("{}");
      return;
    }
    const selected = componentTemplates.find(
      (template) => template.id === componentSelectedTemplateId
    );
    if (!selected) {
      return;
    }
    setComponentTemplateName(selected.name ?? "");
    setComponentTemplateAircraftTemplate(selected.aircraft_template ?? "");
    setComponentTemplateModelCode(selected.model_code ?? "");
    setComponentTemplateOperatorCode(selected.operator_code ?? "");
    setComponentTemplateDefaultsJson(
      JSON.stringify(selected.default_values ?? {}, null, 2)
    );
  }, [componentSelectedTemplateId, componentTemplates]);

  const handlePreviewRowChange = (
    index: number,
    field: keyof AircraftRowData,
    value: string
  ) => {
    setPreviewRows((prev) =>
      prev.map((row, rowIndex) => {
        if (rowIndex !== index) {
          return row;
        }
        const nextData = {
          ...row.data,
          [field]: value,
        };
        const errors = validateRow(nextData);
        return {
          ...row,
          data: nextData,
          errors,
          approved: errors.length === 0 && row.approved,
        };
      })
    );
  };

  const handleComponentPreviewRowChange = (
    index: number,
    field: keyof ComponentRowData,
    value: string
  ) => {
    setComponentPreviewRows((prev) =>
      prev.map((row, rowIndex) => {
        if (rowIndex !== index) {
          return row;
        }
        const nextData = {
          ...row.data,
          [field]: value,
        };
        const errors = validateComponentRow(nextData);
        return {
          ...row,
          data: nextData,
          errors,
          approved: errors.length === 0 && row.approved,
        };
      })
    );
  };

  const toggleApproval = (index: number) => {
    setPreviewRows((prev) =>
      prev.map((row, rowIndex) => {
        if (rowIndex !== index) {
          return row;
        }
        if (hasErrors(row)) {
          return row;
        }
        return {
          ...row,
          approved: !row.approved,
        };
      })
    );
  };

  const toggleComponentApproval = (index: number) => {
    setComponentPreviewRows((prev) =>
      prev.map((row, rowIndex) => {
        if (rowIndex !== index) {
          return row;
        }
        if (hasComponentErrors(row)) {
          return row;
        }
        return {
          ...row,
          approved: !row.approved,
        };
      })
    );
  };

  const submitPreviewFile = async (file: File) => {
    setPreviewLoading(true);
    setMessage(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_BASE}/aircraft/import/preview`, {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail ?? "Preview failed");
      }
      const rows: PreviewRow[] = (data.rows ?? []).map((row: PreviewRow) => ({
        ...row,
        approved: row.errors.length === 0,
      }));
      setPreviewRows(rows);
      setColumnMapping(data.column_mapping ?? null);
      setPreviewSummary(data.summary ?? null);
      setOcrPreview(data.ocr ?? null);
      setOcrTextDraft(data.ocr?.text ?? "");
      setMessage("Preview ready. Review and confirm import.");
    } catch (err: any) {
      setMessage(err.message ?? "Error previewing aircraft.");
    } finally {
      setPreviewLoading(false);
    }
  };

  const submitComponentPreviewFile = async (file: File) => {
    if (!componentAircraftSerial.trim()) {
      setMessage("Enter the aircraft serial number for components.");
      return;
    }
    setComponentPreviewLoading(true);
    setMessage(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(
        `${API_BASE}/aircraft/${encodeURIComponent(
          componentAircraftSerial.trim()
        )}/components/import/preview`,
        {
          method: "POST",
          body: formData,
        }
      );

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail ?? "Component preview failed");
      }
      const rows: ComponentPreviewRow[] = (data.rows ?? []).map(
        (row: ComponentPreviewRow) => ({
          ...row,
          approved: row.errors.length === 0,
        })
      );
      setComponentPreviewRows(rows);
      setComponentColumnMapping(data.column_mapping ?? null);
      setComponentSummary(data.summary ?? null);
      setMessage("Component preview ready. Review and confirm import.");
    } catch (err: any) {
      setMessage(err.message ?? "Error previewing components.");
    } finally {
      setComponentPreviewLoading(false);
    }
  };

  const parseAircraftFile = async () => {
    if (!aircraftFile) {
      setMessage("Select an aircraft file first.");
      return;
    }
    await submitPreviewFile(aircraftFile);
  };

  const parseComponentsFile = async () => {
    if (!componentsFile) {
      setMessage("Select a component file first.");
      return;
    }
    await submitComponentPreviewFile(componentsFile);
  };

  const reparseOcrText = async () => {
    if (!ocrTextDraft.trim()) {
      setMessage("Add corrected OCR text before re-parsing.");
      return;
    }
    const ocrFile = new File([ocrTextDraft], "ocr-corrected.csv", {
      type: "text/csv",
    });
    await submitPreviewFile(ocrFile);
  };

  const parseTemplateDefaults = () => {
    const raw = templateDefaultsJson.trim();
    if (!raw) {
      return null;
    }
    try {
      return JSON.parse(raw);
    } catch (err) {
      throw new Error("Default values JSON is invalid.");
    }
  };

  const parseComponentTemplateDefaults = () => {
    const raw = componentTemplateDefaultsJson.trim();
    if (!raw) {
      return null;
    }
    try {
      return JSON.parse(raw);
    } catch (err) {
      throw new Error("Component default values JSON is invalid.");
    }
  };

  const saveMappingTemplate = async () => {
    if (!columnMapping) {
      setMessage("Parse a file to generate a column mapping before saving.");
      return;
    }
    const name =
      templateName.trim() ||
      templates.find((template) => template.id === selectedTemplateId)?.name ||
      "";
    if (!name) {
      setMessage("Enter a template name.");
      return;
    }

    setTemplateLoading(true);
    setMessage(null);
    try {
      const defaultValues = parseTemplateDefaults();
      const payload = {
        name,
        template_type: "aircraft",
        aircraft_template: templateAircraftTemplate.trim() || null,
        model_code: templateModelCode.trim() || null,
        operator_code: templateOperatorCode.trim() || null,
        column_mapping: columnMapping,
        default_values: defaultValues,
      };
      const method = selectedTemplateId ? "PUT" : "POST";
      const url = selectedTemplateId
        ? `${API_BASE}/aircraft/import/templates/${selectedTemplateId}`
        : `${API_BASE}/aircraft/import/templates`;
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail ?? "Failed to save template.");
      }
      await loadTemplates();
      setSelectedTemplateId(data.id ?? selectedTemplateId);
      setMessage("Template saved.");
    } catch (err: any) {
      setMessage(err.message ?? "Error saving template.");
    } finally {
      setTemplateLoading(false);
    }
  };

  const saveComponentTemplate = async () => {
    if (!componentColumnMapping) {
      setMessage(
        "Parse a file to generate a component column mapping before saving."
      );
      return;
    }
    const name =
      componentTemplateName.trim() ||
      componentTemplates.find(
        (template) => template.id === componentSelectedTemplateId
      )?.name ||
      "";
    if (!name) {
      setMessage("Enter a template name for components.");
      return;
    }

    setComponentTemplateLoading(true);
    setMessage(null);
    try {
      const defaultValues = parseComponentTemplateDefaults();
      const payload = {
        name,
        template_type: "components",
        aircraft_template: componentTemplateAircraftTemplate.trim() || null,
        model_code: componentTemplateModelCode.trim() || null,
        operator_code: componentTemplateOperatorCode.trim() || null,
        column_mapping: componentColumnMapping,
        default_values: defaultValues,
      };
      const method = componentSelectedTemplateId ? "PUT" : "POST";
      const url = componentSelectedTemplateId
        ? `${API_BASE}/aircraft/import/templates/${componentSelectedTemplateId}`
        : `${API_BASE}/aircraft/import/templates`;
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail ?? "Failed to save component template.");
      }
      await loadComponentTemplates();
      setComponentSelectedTemplateId(data.id ?? componentSelectedTemplateId);
      setMessage("Component template saved.");
    } catch (err: any) {
      setMessage(err.message ?? "Error saving component template.");
    } finally {
      setComponentTemplateLoading(false);
    }
  };

  const applyTemplateToPreview = () => {
    const selected = templates.find(
      (template) => template.id === selectedTemplateId
    );
    if (!selected) {
      setMessage("Select a template to apply.");
      return;
    }
    setPreviewRows((prev) =>
      prev.map((row) => {
        const nextData = { ...row.data };
        const defaults = selected.default_values ?? {};

        if (selected.aircraft_template && !nextData.template?.trim()) {
          nextData.template = selected.aircraft_template;
        }
        if (selected.model_code && !nextData.aircraft_model_code?.trim()) {
          nextData.aircraft_model_code = selected.model_code;
        }
        if (selected.operator_code && !nextData.operator_code?.trim()) {
          nextData.operator_code = selected.operator_code;
        }

        (Object.entries(defaults) as [keyof AircraftRowData, any][]).forEach(
          ([key, value]) => {
            if (value === null || value === undefined) {
              return;
            }
            const currentValue = nextData[key];
            if (
              currentValue === null ||
              currentValue === undefined ||
              `${currentValue}`.trim() === ""
            ) {
              nextData[key] = value;
            }
          }
        );

        const errors = validateRow(nextData);
        return {
          ...row,
          data: nextData,
          errors,
          approved: errors.length === 0 && row.approved,
        };
      })
    );
    setMessage("Template defaults applied to preview rows.");
  };

  const applyComponentTemplateToPreview = () => {
    const selected = componentTemplates.find(
      (template) => template.id === componentSelectedTemplateId
    );
    if (!selected) {
      setMessage("Select a component template to apply.");
      return;
    }
    setComponentPreviewRows((prev) =>
      prev.map((row) => {
        const nextData = { ...row.data };
        const defaults = selected.default_values ?? {};

        (Object.entries(defaults) as [keyof ComponentRowData, any][]).forEach(
          ([key, value]) => {
            if (value === null || value === undefined) {
              return;
            }
            const currentValue = nextData[key];
            if (
              currentValue === null ||
              currentValue === undefined ||
              `${currentValue}`.trim() === ""
            ) {
              nextData[key] = value;
            }
          }
        );

        const errors = validateComponentRow(nextData);
        return {
          ...row,
          data: nextData,
          errors,
          approved: errors.length === 0 && row.approved,
        };
      })
    );
    setMessage("Component template defaults applied.");
  };

  const confirmImport = async () => {
    const approvedRows = previewRows.filter(
      (row) => row.approved && row.errors.length === 0
    );
    if (approvedRows.length === 0) {
      setMessage("Select at least one valid row to import.");
      return;
    }
    setConfirmLoading(true);
    setMessage(null);

    try {
      const res = await fetch(`${API_BASE}/aircraft/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rows: approvedRows.map((row) => ({
            row_number: row.row_number,
            ...row.data,
          })),
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail ?? "Import failed");
      }
      setMessage(
        `Aircraft import OK. Created: ${data.created}, Updated: ${data.updated}`
      );
    } catch (err: any) {
      setMessage(err.message ?? "Error importing aircraft.");
    } finally {
      setConfirmLoading(false);
    }
  };

  const confirmComponentImport = async () => {
    if (!componentAircraftSerial.trim()) {
      setMessage("Enter the aircraft serial number for components.");
      return;
    }
    const approvedRows = componentPreviewRows.filter(
      (row) => row.approved && row.errors.length === 0
    );
    if (approvedRows.length === 0) {
      setMessage("Select at least one valid component row to import.");
      return;
    }
    setComponentConfirmLoading(true);
    setMessage(null);

    try {
      const res = await fetch(
        `${API_BASE}/aircraft/${encodeURIComponent(
          componentAircraftSerial.trim()
        )}/components/import/confirm`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            rows: approvedRows.map((row) => ({
              row_number: row.row_number,
              ...row.data,
            })),
          }),
        }
      );

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail ?? "Component import failed");
      }
      setMessage(
        `Components import OK for aircraft ${data.aircraft_serial_number}. ` +
          `Created: ${data.components_created}, Updated: ${data.components_updated}`
      );
    } catch (err: any) {
      setMessage(err.message ?? "Error importing components.");
    } finally {
      setComponentConfirmLoading(false);
    }
  };

  const approvedCount = useMemo(
    () => previewRows.filter((row) => row.approved && !hasErrors(row)).length,
    [previewRows]
  );

  const componentApprovedCount = useMemo(
    () =>
      componentPreviewRows.filter(
        (row) => row.approved && !hasComponentErrors(row)
      ).length,
    [componentPreviewRows]
  );

  return (
    <div className="min-h-screen bg-slate-950 text-slate-50 flex flex-col items-center py-10">
      <div className="w-full max-w-6xl space-y-8">
        <h1 className="text-2xl font-semibold">Aircraft Loader / Setup</h1>

        {/* AIRCRAFT MASTER IMPORT */}
        <section className="bg-slate-900 rounded-2xl p-6 shadow">
          <h2 className="text-lg font-semibold mb-2">
            1. Import Aircraft Master List
          </h2>
          <p className="text-sm text-slate-300 mb-4">
            Upload a CSV or Excel file containing all aircraft
            (serial, registration, type, model, base, hours, cycles).
          </p>

          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <input
              type="file"
              accept=".csv,.txt,.xlsx,.xlsm,.xls,.pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp"
              onChange={handleAircraftFileChange}
              className="block"
            />

            <div className="flex flex-wrap gap-3">
              <button
                onClick={parseAircraftFile}
                disabled={previewLoading}
                className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50"
              >
                {previewLoading ? "Parsing..." : "Parse & Preview"}
              </button>
              <button
                onClick={confirmImport}
                disabled={confirmLoading || approvedCount === 0}
                className="px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 disabled:opacity-50"
              >
                {confirmLoading
                  ? "Importing..."
                  : `Confirm Import (${approvedCount})`}
              </button>
            </div>
          </div>

          {ocrPreview && (
            <div className="mt-4 rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-xs uppercase text-slate-400">
                    OCR Preview
                  </div>
                  <div className="text-sm text-slate-200">
                    {ocrPreview.file_type
                      ? `Detected ${ocrPreview.file_type.toUpperCase()}`
                      : "Detected OCR content"}
                  </div>
                </div>
                <div className="text-sm text-slate-200">
                  Confidence:{" "}
                  <span className="font-semibold">
                    {ocrPreview.confidence !== null &&
                    ocrPreview.confidence !== undefined
                      ? `${ocrPreview.confidence.toFixed(1)}%`
                      : "n/a"}
                  </span>
                </div>
              </div>

              {ocrPreview.samples && ocrPreview.samples.length > 0 && (
                <div className="mt-3 text-sm text-slate-300">
                  <div className="text-xs uppercase text-slate-400">
                    Extracted Samples
                  </div>
                  <ul className="mt-1 list-disc space-y-1 pl-5">
                    {ocrPreview.samples.map((sample, index) => (
                      <li key={`${sample}-${index}`}>{sample}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="mt-4">
                <label className="block text-xs uppercase text-slate-400">
                  OCR Text (edit to correct before re-parsing)
                </label>
                <textarea
                  value={ocrTextDraft}
                  onChange={(e) => setOcrTextDraft(e.target.value)}
                  rows={6}
                  className="mt-1 w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-slate-100 font-mono text-xs"
                />
                <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-400">
                  <span>
                    Re-parsing expects CSV/TSV-style rows with a header line.
                  </span>
                </div>
                <button
                  onClick={reparseOcrText}
                  disabled={previewLoading}
                  className="mt-3 px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 disabled:opacity-50"
                >
                  {previewLoading ? "Re-parsing..." : "Rebuild Preview from OCR"}
                </button>
              </div>
            </div>
          )}

          <div className="mt-4 grid gap-3 rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div className="flex flex-col gap-1">
                <label className="text-xs uppercase text-slate-400">
                  Template
                </label>
                <select
                  value={selectedTemplateId}
                  onChange={(e) =>
                    setSelectedTemplateId(
                      e.target.value ? Number(e.target.value) : ""
                    )
                  }
                  className="rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-slate-100"
                >
                  <option value="">Select template</option>
                  {templates.map((template) => (
                    <option key={template.id} value={template.id}>
                      {template.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-wrap gap-3">
                <button
                  onClick={applyTemplateToPreview}
                  disabled={!previewRows.length || !selectedTemplateId}
                  className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50"
                >
                  Apply Template to Preview
                </button>
                <button
                  onClick={saveMappingTemplate}
                  disabled={templateLoading || !columnMapping}
                  className="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 disabled:opacity-50"
                >
                  {templateLoading ? "Saving..." : "Save Mapping as Template"}
                </button>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-4">
              <div>
                <label className="block text-xs uppercase text-slate-400">
                  Template Name
                </label>
                <input
                  type="text"
                  value={templateName}
                  onChange={(e) => setTemplateName(e.target.value)}
                  className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-slate-100"
                />
              </div>
              <div>
                <label className="block text-xs uppercase text-slate-400">
                  Aircraft Template
                </label>
                <input
                  type="text"
                  value={templateAircraftTemplate}
                  onChange={(e) => setTemplateAircraftTemplate(e.target.value)}
                  className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-slate-100"
                />
              </div>
              <div>
                <label className="block text-xs uppercase text-slate-400">
                  Model Code
                </label>
                <input
                  type="text"
                  value={templateModelCode}
                  onChange={(e) => setTemplateModelCode(e.target.value)}
                  className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-slate-100"
                />
              </div>
              <div>
                <label className="block text-xs uppercase text-slate-400">
                  Operator Code
                </label>
                <input
                  type="text"
                  value={templateOperatorCode}
                  onChange={(e) => setTemplateOperatorCode(e.target.value)}
                  className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-slate-100"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs uppercase text-slate-400">
                Default Values (JSON)
              </label>
              <textarea
                value={templateDefaultsJson}
                onChange={(e) => setTemplateDefaultsJson(e.target.value)}
                rows={4}
                className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-slate-100 font-mono text-xs"
              />
            </div>
          </div>

          {previewSummary && (
            <div className="mt-4 grid gap-2 text-sm text-slate-200 md:grid-cols-3">
              <div className="rounded-xl bg-slate-950 border border-slate-800 p-3">
                <div className="text-xs uppercase text-slate-400">New</div>
                <div className="text-lg font-semibold">
                  {previewSummary.new}
                </div>
              </div>
              <div className="rounded-xl bg-slate-950 border border-slate-800 p-3">
                <div className="text-xs uppercase text-slate-400">Update</div>
                <div className="text-lg font-semibold">
                  {previewSummary.update}
                </div>
              </div>
              <div className="rounded-xl bg-slate-950 border border-slate-800 p-3">
                <div className="text-xs uppercase text-slate-400">Invalid</div>
                <div className="text-lg font-semibold">
                  {previewSummary.invalid}
                </div>
              </div>
            </div>
          )}

          {previewRows.length > 0 && (
            <div className="mt-6 overflow-x-auto border border-slate-800 rounded-2xl">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-950 text-slate-200">
                  <tr>
                    <th className="p-3 text-left">Approve</th>
                    <th className="p-3 text-left">Row</th>
                    <th className="p-3 text-left">Action</th>
                    <th className="p-3 text-left">Serial</th>
                    <th className="p-3 text-left">Registration</th>
                    <th className="p-3 text-left">Template</th>
                    <th className="p-3 text-left">Suggested Template</th>
                    <th className="p-3 text-left">Make</th>
                    <th className="p-3 text-left">Model</th>
                    <th className="p-3 text-left">Base</th>
                    <th className="p-3 text-left">Owner</th>
                    <th className="p-3 text-left">Hours</th>
                    <th className="p-3 text-left">Cycles</th>
                    <th className="p-3 text-left">Last Log Date</th>
                  </tr>
                </thead>
                <tbody>
                  {previewRows.map((row, index) => {
                    const action =
                      row.errors.length > 0 ? "invalid" : row.action;
                    const serialMissing = !row.data.serial_number?.trim();
                    const regMissing = !row.data.registration?.trim();
                    return (
                      <tr
                        key={`${row.row_number}-${index}`}
                        className="border-t border-slate-800"
                      >
                        <td className="p-3">
                          <input
                            type="checkbox"
                            checked={row.approved}
                            disabled={hasErrors(row)}
                            onChange={() => toggleApproval(index)}
                          />
                        </td>
                        <td className="p-3 text-slate-300">{row.row_number}</td>
                        <td className="p-3">
                          <span
                            className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-semibold ${
                              action === "new"
                                ? "bg-emerald-500/20 text-emerald-200"
                                : action === "update"
                                ? "bg-sky-500/20 text-sky-200"
                                : "bg-rose-500/20 text-rose-200"
                            }`}
                          >
                            {action}
                          </span>
                          {row.errors.length > 0 && (
                            <div className="mt-1 text-xs text-rose-300">
                              {row.errors.join(" ")}
                            </div>
                          )}
                          {row.warnings.length > 0 && (
                            <div className="mt-1 text-xs text-amber-200">
                              {row.warnings.join(" ")}
                            </div>
                          )}
                        </td>
                        <td className="p-3">
                          <input
                            type="text"
                            value={row.data.serial_number ?? ""}
                            onChange={(e) =>
                              handlePreviewRowChange(
                                index,
                                "serial_number",
                                e.target.value
                              )
                            }
                            className={`w-32 rounded-lg bg-slate-950 border px-2 py-1 text-slate-100 ${
                              serialMissing
                                ? "border-rose-400"
                                : "border-slate-700"
                            }`}
                          />
                        </td>
                        <td className="p-3">
                          <input
                            type="text"
                            value={row.data.registration ?? ""}
                            onChange={(e) =>
                              handlePreviewRowChange(
                                index,
                                "registration",
                                e.target.value
                              )
                            }
                            className={`w-32 rounded-lg bg-slate-950 border px-2 py-1 text-slate-100 ${
                              regMissing
                                ? "border-rose-400"
                                : "border-slate-700"
                            }`}
                          />
                        </td>
                        <td className="p-3">
                          <input
                            type="text"
                            value={row.data.template ?? ""}
                            onChange={(e) =>
                              handlePreviewRowChange(
                                index,
                                "template",
                                e.target.value
                              )
                            }
                            className="w-32 rounded-lg bg-slate-950 border border-slate-700 px-2 py-1 text-slate-100"
                          />
                        </td>
                        <td className="p-3 text-xs text-slate-300">
                          {row.suggested_template ? (
                            <div>
                              <div className="font-semibold text-slate-100">
                                {row.suggested_template.name}
                              </div>
                              <div>
                                {(row.suggested_template.aircraft_template ||
                                  row.suggested_template.model_code ||
                                  row.suggested_template.operator_code) && (
                                  <span className="text-slate-400">
                                    {[
                                      row.suggested_template.aircraft_template,
                                      row.suggested_template.model_code,
                                      row.suggested_template.operator_code,
                                    ]
                                      .filter(Boolean)
                                      .join(" · ")}
                                  </span>
                                )}
                              </div>
                            </div>
                          ) : (
                            <span className="text-slate-500">—</span>
                          )}
                        </td>
                        <td className="p-3">
                          <input
                            type="text"
                            value={row.data.make ?? ""}
                            onChange={(e) =>
                              handlePreviewRowChange(
                                index,
                                "make",
                                e.target.value
                              )
                            }
                            className="w-32 rounded-lg bg-slate-950 border border-slate-700 px-2 py-1 text-slate-100"
                          />
                        </td>
                        <td className="p-3">
                          <input
                            type="text"
                            value={row.data.model ?? ""}
                            onChange={(e) =>
                              handlePreviewRowChange(
                                index,
                                "model",
                                e.target.value
                              )
                            }
                            className="w-32 rounded-lg bg-slate-950 border border-slate-700 px-2 py-1 text-slate-100"
                          />
                        </td>
                        <td className="p-3">
                          <input
                            type="text"
                            value={row.data.home_base ?? ""}
                            onChange={(e) =>
                              handlePreviewRowChange(
                                index,
                                "home_base",
                                e.target.value
                              )
                            }
                            className="w-32 rounded-lg bg-slate-950 border border-slate-700 px-2 py-1 text-slate-100"
                          />
                        </td>
                        <td className="p-3">
                          <input
                            type="text"
                            value={row.data.owner ?? ""}
                            onChange={(e) =>
                              handlePreviewRowChange(
                                index,
                                "owner",
                                e.target.value
                              )
                            }
                            className="w-32 rounded-lg bg-slate-950 border border-slate-700 px-2 py-1 text-slate-100"
                          />
                        </td>
                        <td className="p-3">
                          <input
                            type="number"
                            value={row.data.total_hours ?? ""}
                            onChange={(e) =>
                              handlePreviewRowChange(
                                index,
                                "total_hours",
                                e.target.value
                              )
                            }
                            className="w-28 rounded-lg bg-slate-950 border border-slate-700 px-2 py-1 text-slate-100"
                          />
                        </td>
                        <td className="p-3">
                          <input
                            type="number"
                            value={row.data.total_cycles ?? ""}
                            onChange={(e) =>
                              handlePreviewRowChange(
                                index,
                                "total_cycles",
                                e.target.value
                              )
                            }
                            className="w-24 rounded-lg bg-slate-950 border border-slate-700 px-2 py-1 text-slate-100"
                          />
                        </td>
                        <td className="p-3">
                          <input
                            type="date"
                            value={row.data.last_log_date ?? ""}
                            onChange={(e) =>
                              handlePreviewRowChange(
                                index,
                                "last_log_date",
                                e.target.value
                              )
                            }
                            className="w-36 rounded-lg bg-slate-950 border border-slate-700 px-2 py-1 text-slate-100"
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {columnMapping && (
            <div className="mt-4 text-xs text-slate-400">
              Detected mapping:{" "}
              {Object.entries(columnMapping)
                .filter(([, value]) => value)
                .map(([key, value]) => `${key} → ${value}`)
                .join(", ")}
            </div>
          )}
        </section>

        {/* COMPONENT IMPORT */}
        <section className="bg-slate-900 rounded-2xl p-6 shadow">
          <h2 className="text-lg font-semibold mb-2">
            2. Import Components for One Aircraft
          </h2>
          <p className="text-sm text-slate-300 mb-4">
            Upload CSV/Excel with component positions (e.g. L ENGINE, R ENGINE,
            APU), part and serial numbers, installed values, etc.
          </p>

          <div className="mb-3">
            <label className="block text-sm mb-1">
              Aircraft Serial Number (e.g. 574, 510, 331)
            </label>
            <input
              type="text"
              value={componentAircraftSerial}
              onChange={(e) => setComponentAircraftSerial(e.target.value)}
              className="w-full rounded-xl px-3 py-2 bg-slate-950 border border-slate-700"
            />
          </div>

          <input
            type="file"
            accept=".csv,.txt,.xlsx,.xlsm,.xls,.pdf"
            onChange={handleComponentsFileChange}
            className="block mb-3"
          />

          <div className="flex flex-wrap gap-3">
            <button
              onClick={parseComponentsFile}
              disabled={componentPreviewLoading}
              className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50"
            >
              {componentPreviewLoading ? "Parsing..." : "Parse & Preview"}
            </button>
            <button
              onClick={confirmComponentImport}
              disabled={componentConfirmLoading || componentApprovedCount === 0}
              className="px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 disabled:opacity-50"
            >
              {componentConfirmLoading
                ? "Importing..."
                : `Confirm Import (${componentApprovedCount})`}
            </button>
          </div>

          <div className="mt-4 grid gap-3 rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div className="flex flex-col gap-1">
                <label className="text-xs uppercase text-slate-400">
                  Component Template
                </label>
                <select
                  value={componentSelectedTemplateId}
                  onChange={(e) =>
                    setComponentSelectedTemplateId(
                      e.target.value ? Number(e.target.value) : ""
                    )
                  }
                  className="rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-slate-100"
                >
                  <option value="">Select template</option>
                  {componentTemplates.map((template) => (
                    <option key={template.id} value={template.id}>
                      {template.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-wrap gap-3">
                <button
                  onClick={applyComponentTemplateToPreview}
                  disabled={!componentPreviewRows.length || !componentSelectedTemplateId}
                  className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50"
                >
                  Apply Template to Preview
                </button>
                <button
                  onClick={saveComponentTemplate}
                  disabled={componentTemplateLoading || !componentColumnMapping}
                  className="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 disabled:opacity-50"
                >
                  {componentTemplateLoading
                    ? "Saving..."
                    : "Save Mapping as Template"}
                </button>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-4">
              <div>
                <label className="block text-xs uppercase text-slate-400">
                  Template Name
                </label>
                <input
                  type="text"
                  value={componentTemplateName}
                  onChange={(e) => setComponentTemplateName(e.target.value)}
                  className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-slate-100"
                />
              </div>
              <div>
                <label className="block text-xs uppercase text-slate-400">
                  Aircraft Template
                </label>
                <input
                  type="text"
                  value={componentTemplateAircraftTemplate}
                  onChange={(e) =>
                    setComponentTemplateAircraftTemplate(e.target.value)
                  }
                  className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-slate-100"
                />
              </div>
              <div>
                <label className="block text-xs uppercase text-slate-400">
                  Model Code
                </label>
                <input
                  type="text"
                  value={componentTemplateModelCode}
                  onChange={(e) => setComponentTemplateModelCode(e.target.value)}
                  className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-slate-100"
                />
              </div>
              <div>
                <label className="block text-xs uppercase text-slate-400">
                  Operator Code
                </label>
                <input
                  type="text"
                  value={componentTemplateOperatorCode}
                  onChange={(e) =>
                    setComponentTemplateOperatorCode(e.target.value)
                  }
                  className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-slate-100"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs uppercase text-slate-400">
                Default Values (JSON)
              </label>
              <textarea
                value={componentTemplateDefaultsJson}
                onChange={(e) =>
                  setComponentTemplateDefaultsJson(e.target.value)
                }
                rows={4}
                className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-slate-100 font-mono text-xs"
              />
            </div>
          </div>

          {componentSummary && (
            <div className="mt-4 grid gap-2 text-sm text-slate-200 md:grid-cols-3">
              <div className="rounded-xl bg-slate-950 border border-slate-800 p-3">
                <div className="text-xs uppercase text-slate-400">New</div>
                <div className="text-lg font-semibold">
                  {componentSummary.new}
                </div>
              </div>
              <div className="rounded-xl bg-slate-950 border border-slate-800 p-3">
                <div className="text-xs uppercase text-slate-400">Update</div>
                <div className="text-lg font-semibold">
                  {componentSummary.update}
                </div>
              </div>
              <div className="rounded-xl bg-slate-950 border border-slate-800 p-3">
                <div className="text-xs uppercase text-slate-400">Invalid</div>
                <div className="text-lg font-semibold">
                  {componentSummary.invalid}
                </div>
              </div>
            </div>
          )}

          {componentPreviewRows.length > 0 && (
            <div className="mt-6 overflow-x-auto border border-slate-800 rounded-2xl">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-950 text-slate-200">
                  <tr>
                    <th className="p-3 text-left">Approve</th>
                    <th className="p-3 text-left">Row</th>
                    <th className="p-3 text-left">Action</th>
                    <th className="p-3 text-left">Position</th>
                    <th className="p-3 text-left">Part Number</th>
                    <th className="p-3 text-left">Serial Number</th>
                    <th className="p-3 text-left">Existing PN/SN</th>
                    <th className="p-3 text-left">ATA</th>
                    <th className="p-3 text-left">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {componentPreviewRows.map((row, index) => {
                    const action =
                      row.errors.length > 0 ? "invalid" : row.action;
                    const positionMissing = !row.data.position?.trim();
                    const existingPart = row.existing_component?.part_number;
                    const existingSerial = row.existing_component?.serial_number;
                    const partDiff =
                      existingPart &&
                      row.data.part_number &&
                      existingPart !== row.data.part_number;
                    const serialDiff =
                      existingSerial &&
                      row.data.serial_number &&
                      existingSerial !== row.data.serial_number;
                    return (
                      <tr
                        key={`${row.row_number}-${index}`}
                        className="border-t border-slate-800"
                      >
                        <td className="p-3">
                          <input
                            type="checkbox"
                            checked={row.approved}
                            disabled={hasComponentErrors(row)}
                            onChange={() => toggleComponentApproval(index)}
                          />
                        </td>
                        <td className="p-3 text-slate-300">{row.row_number}</td>
                        <td className="p-3">
                          <span
                            className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-semibold ${
                              action === "new"
                                ? "bg-emerald-500/20 text-emerald-200"
                                : action === "update"
                                ? "bg-sky-500/20 text-sky-200"
                                : "bg-rose-500/20 text-rose-200"
                            }`}
                          >
                            {action}
                          </span>
                          {row.errors.length > 0 && (
                            <div className="mt-1 text-xs text-rose-300">
                              {row.errors.join(" ")}
                            </div>
                          )}
                          {row.warnings.length > 0 && (
                            <div className="mt-1 text-xs text-amber-200">
                              {row.warnings.join(" ")}
                            </div>
                          )}
                          {row.dedupe_suggestions &&
                            row.dedupe_suggestions.length > 0 && (
                              <div className="mt-1 text-xs text-amber-200">
                                {row.dedupe_suggestions.map((suggestion, idx) => (
                                  <div key={`${row.row_number}-dedupe-${idx}`}>
                                    {suggestion.source === "existing"
                                      ? "Existing"
                                      : "File"}{" "}
                                    match for {suggestion.part_number}/
                                    {suggestion.serial_number}:{" "}
                                    {suggestion.positions.join(", ")}
                                  </div>
                                ))}
                              </div>
                            )}
                        </td>
                        <td className="p-3">
                          <input
                            type="text"
                            value={row.data.position ?? ""}
                            onChange={(e) =>
                              handleComponentPreviewRowChange(
                                index,
                                "position",
                                e.target.value
                              )
                            }
                            className={`w-32 rounded-lg bg-slate-950 border px-2 py-1 text-slate-100 ${
                              positionMissing
                                ? "border-rose-400"
                                : "border-slate-700"
                            }`}
                          />
                        </td>
                        <td className="p-3">
                          <input
                            type="text"
                            value={row.data.part_number ?? ""}
                            onChange={(e) =>
                              handleComponentPreviewRowChange(
                                index,
                                "part_number",
                                e.target.value
                              )
                            }
                            className={`w-32 rounded-lg bg-slate-950 border px-2 py-1 text-slate-100 ${
                              partDiff ? "border-amber-400" : "border-slate-700"
                            }`}
                          />
                        </td>
                        <td className="p-3">
                          <input
                            type="text"
                            value={row.data.serial_number ?? ""}
                            onChange={(e) =>
                              handleComponentPreviewRowChange(
                                index,
                                "serial_number",
                                e.target.value
                              )
                            }
                            className={`w-32 rounded-lg bg-slate-950 border px-2 py-1 text-slate-100 ${
                              serialDiff
                                ? "border-amber-400"
                                : "border-slate-700"
                            }`}
                          />
                        </td>
                        <td className="p-3 text-xs text-slate-300">
                          {existingPart || existingSerial ? (
                            <div>
                              <div>{existingPart ?? "—"}</div>
                              <div className="text-slate-400">
                                {existingSerial ?? "—"}
                              </div>
                            </div>
                          ) : (
                            <span className="text-slate-500">—</span>
                          )}
                        </td>
                        <td className="p-3">
                          <input
                            type="text"
                            value={row.data.ata ?? ""}
                            onChange={(e) =>
                              handleComponentPreviewRowChange(
                                index,
                                "ata",
                                e.target.value
                              )
                            }
                            className="w-20 rounded-lg bg-slate-950 border border-slate-700 px-2 py-1 text-slate-100"
                          />
                        </td>
                        <td className="p-3">
                          <input
                            type="text"
                            value={row.data.notes ?? ""}
                            onChange={(e) =>
                              handleComponentPreviewRowChange(
                                index,
                                "notes",
                                e.target.value
                              )
                            }
                            className="w-40 rounded-lg bg-slate-950 border border-slate-700 px-2 py-1 text-slate-100"
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {componentColumnMapping && (
            <div className="mt-4 text-xs text-slate-400">
              Detected mapping:{" "}
              {Object.entries(componentColumnMapping)
                .filter(([, value]) => value)
                .map(([key, value]) => `${key} → ${value}`)
                .join(", ")}
            </div>
          )}
        </section>

        {message && (
          <div className="mt-4 text-sm bg-slate-900 border border-slate-700 rounded-2xl p-3">
            {message}
          </div>
        )}
      </div>
    </div>
  );
};

export default AircraftImportPage;
