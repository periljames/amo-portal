// frontend/src/pages/AircraftImportPage.tsx
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type {
  CellValueChangedEvent,
  ColDef,
  GridReadyEvent,
  ICellRendererParams,
} from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";
import { getCachedUser } from "../services/auth";
import {
  getActiveAmoId as getAdminActiveAmoId,
  listAdminAmos,
  setActiveAmoId as setAdminActiveAmoId,
  type AdminAmoRead,
} from "../services/adminUsers";

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

type AircraftRowField = keyof AircraftRowData;

type PreviewRow = {
  row_number: number;
  data: AircraftRowData;
  errors: string[];
  warnings: string[];
  action: "new" | "update" | "invalid";
  approved: boolean;
  suggested_template?: SuggestedTemplate | null;
  original_data?: AircraftRowData;
  proposed_fields?: AircraftRowField[];
  user_overrides?: AircraftRowField[];
  formula_proposals?: FormulaProposal[];
  formula_decisions?: Partial<Record<AircraftRowField, FormulaDecision>>;
};

type ConfirmedCell = {
  original: any;
  proposed: any;
  final: any;
  decision?: FormulaDecision;
};

type ConfirmedRow = {
  row_number: number;
  cells: Record<string, ConfirmedCell>;
};

type SuggestedTemplate = {
  id: number;
  name: string;
  aircraft_template?: string | null;
  model_code?: string | null;
  operator_code?: string | null;
};

type FormulaProposal = {
  cell_address?: string | null;
  column_name: string;
  current_value: any;
  proposed_value: any;
  confidence?: string | null;
};

type FormulaDecision = "accept" | "keep" | "override";

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

type ImportSnapshot = {
  id: number;
  batch_id: string;
  import_type: string;
  diff_map: Record<string, any>;
  created_at: string;
  created_by_user_id?: string | null;
};

const MAX_CLIENT_PREVIEW_ROWS = 1500;

const AIRCRAFT_DIFF_FIELDS: AircraftRowField[] = [
  "serial_number",
  "registration",
  "template",
  "make",
  "model",
  "home_base",
  "owner",
  "total_hours",
  "total_cycles",
  "last_log_date",
];

const AIRCRAFT_FIELD_LABELS: Record<AircraftRowField, string> = {
  serial_number: "Serial",
  registration: "Registration",
  template: "Template",
  make: "Make",
  model: "Model",
  home_base: "Base",
  owner: "Owner",
  aircraft_model_code: "Model Code",
  operator_code: "Operator Code",
  supplier_code: "Supplier Code",
  company_name: "Company Name",
  internal_aircraft_identifier: "Internal ID",
  status: "Status",
  is_active: "Active",
  last_log_date: "Last Log Date",
  total_hours: "Hours",
  total_cycles: "Cycles",
};

const FORMULA_TOLERANCE = 0.01;

const normalizeValue = (value: unknown) =>
  value === null || value === undefined ? "" : `${value}`.trim();

const normalizeHeader = (value: string) =>
  value
    .trim()
    .toLowerCase()
    .replace(/[.\-/\s]+/g, "_")
    .replace(/_+/g, "_");

const isSuperuser = (user: any): boolean => {
  if (!user) return false;
  return !!user.is_superuser || user.role === "SUPERUSER";
};

const AircraftImportPage: React.FC = () => {
  const navigate = useNavigate();
  const { amoCode, department } = useParams<{
    amoCode?: string;
    department?: string;
  }>();
  const [aircraftFile, setAircraftFile] = useState<File | null>(null);
  const [componentsFile, setComponentsFile] = useState<File | null>(null);
  const [componentAircraftSerial, setComponentAircraftSerial] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [amoOptions, setAmoOptions] = useState<AdminAmoRead[]>([]);
  const [amoLoading, setAmoLoading] = useState(false);
  const [amoError, setAmoError] = useState<string | null>(null);
  const [selectedAmoId, setSelectedAmoId] = useState<string>("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [aircraftImportComplete, setAircraftImportComplete] = useState(false);
  const [previewRows, setPreviewRows] = useState<PreviewRow[]>([]);
  const [previewRowOverrides, setPreviewRowOverrides] = useState<
    Record<number, PreviewRow>
  >({});
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
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [previewTotalRows, setPreviewTotalRows] = useState(0);
  const [previewMode, setPreviewMode] = useState<"client" | "server">("client");
  const [previewGridApi, setPreviewGridApi] = useState<any>(null);
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
  const [componentImportComplete, setComponentImportComplete] = useState(false);
  const [importBatchId, setImportBatchId] = useState<string | null>(null);
  const [snapshots, setSnapshots] = useState<ImportSnapshot[]>([]);
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<number | null>(
    null
  );
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [snapshotActionLoading, setSnapshotActionLoading] = useState(false);

  const currentUser = getCachedUser();
  const userIsSuperuser = isSuperuser(currentUser);
  const currentDepartment = department || "planning";

  const handleAircraftFileChange = (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    setAircraftFile(e.target.files?.[0] ?? null);
    setAircraftImportComplete(false);
  };

  const handleComponentsFileChange = (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    setComponentsFile(e.target.files?.[0] ?? null);
    setComponentImportComplete(false);
  };

  const handleAmoChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const nextId = event.target.value;
    setSelectedAmoId(nextId);
    if (nextId) {
      setAdminActiveAmoId(nextId);
    }
    const amo = amoOptions.find((entry) => entry.id === nextId);
    if (amo?.login_slug) {
      navigate(
        `/maintenance/${amo.login_slug}/${currentDepartment}/aircraft-import`
      );
    }
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

  const normalizePreviewRow = (row: PreviewRow): PreviewRow => ({
    ...row,
    approved: row.errors.length === 0,
    original_data: { ...row.data },
    proposed_fields: row.proposed_fields ?? [],
    user_overrides: row.user_overrides ?? [],
    formula_proposals: row.formula_proposals ?? [],
    formula_decisions: row.formula_decisions ?? {},
  });

  const mergePreviewOverride = (row: PreviewRow): PreviewRow => {
    const override = previewRowOverrides[row.row_number];
    if (!override) {
      return row;
    }
    return {
      ...row,
      ...override,
      data: { ...row.data, ...override.data },
      errors: override.errors ?? row.errors,
      warnings: override.warnings ?? row.warnings,
      approved: override.approved ?? row.approved,
      original_data: override.original_data ?? row.original_data,
      proposed_fields: override.proposed_fields ?? row.proposed_fields,
      user_overrides: override.user_overrides ?? row.user_overrides,
      formula_decisions: override.formula_decisions ?? row.formula_decisions,
      formula_proposals: override.formula_proposals ?? row.formula_proposals,
    };
  };

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
    if (!userIsSuperuser) return;
    let active = true;

    const loadAmos = async () => {
      setAmoLoading(true);
      setAmoError(null);
      try {
        const data = await listAdminAmos();
        if (!active) return;
        setAmoOptions(data ?? []);
      } catch (err: any) {
        if (!active) return;
        setAmoError(err?.message ?? "Could not load AMO list.");
      } finally {
        if (active) setAmoLoading(false);
      }
    };

    void loadAmos();
    return () => {
      active = false;
    };
  }, [userIsSuperuser]);

  useEffect(() => {
    if (!userIsSuperuser || amoOptions.length === 0) return;
    const storedAmoId = getAdminActiveAmoId();
    const matchBySlug = amoCode
      ? amoOptions.find((amo) => amo.login_slug === amoCode)
      : undefined;
    const nextId = storedAmoId || matchBySlug?.id || amoOptions[0]?.id || "";
    if (nextId && nextId !== selectedAmoId) {
      setSelectedAmoId(nextId);
      setAdminActiveAmoId(nextId);
    }
  }, [userIsSuperuser, amoOptions, amoCode, selectedAmoId]);

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

  const updatePreviewRowValue = (
    rowNumber: number,
    field: AircraftRowField,
    value: any,
    source: "user" | "system" = "user",
    decision?: FormulaDecision,
    rowContext?: PreviewRow
  ) => {
    const applyUpdate = (row: PreviewRow) => {
      const nextData = {
        ...row.data,
        [field]: value,
      };
      const errors = validateRow(nextData);
      const originalValue = normalizeValue(row.original_data?.[field]);
      const userOverrides = new Set(row.user_overrides ?? []);
      if (source === "user") {
        if (normalizeValue(value) === originalValue) {
          userOverrides.delete(field);
        } else {
          userOverrides.add(field);
        }
      }
      const formulaDecisions = { ...(row.formula_decisions ?? {}) };
      if (decision) {
        formulaDecisions[field] = decision;
      }
      return {
        ...row,
        data: nextData,
        errors,
        approved: errors.length === 0 && row.approved,
        user_overrides: Array.from(userOverrides),
        formula_decisions: formulaDecisions,
      };
    };

    if (previewMode === "client") {
      setPreviewRows((prev) =>
        prev.map((row) => {
          if (row.row_number !== rowNumber) {
            return row;
          }
          return applyUpdate(row);
        })
      );
      return;
    }

    if (!rowContext) {
      return;
    }
    setPreviewRowOverrides((prev) => ({
      ...prev,
      [rowNumber]: applyUpdate(rowContext),
    }));
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

  const toggleApproval = (row: PreviewRow) => {
    if (hasErrors(row)) {
      return;
    }
    if (previewMode === "client") {
      setPreviewRows((prev) =>
        prev.map((entry) => {
          if (entry.row_number !== row.row_number) {
            return entry;
          }
          return {
            ...entry,
            approved: !entry.approved,
          };
        })
      );
      return;
    }
    setPreviewRowOverrides((prev) => ({
      ...prev,
      [row.row_number]: {
        ...row,
        approved: !row.approved,
      },
    }));
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
      const rows: PreviewRow[] = (data.rows ?? []).map((row: PreviewRow) =>
        normalizePreviewRow(row)
      );
      const totalRows = data.total_rows ?? rows.length;
      const nextMode =
        totalRows > MAX_CLIENT_PREVIEW_ROWS ? "server" : "client";
      setPreviewRows(rows);
      setPreviewRowOverrides({});
      setPreviewId(data.preview_id ?? null);
      setPreviewTotalRows(totalRows);
      setPreviewMode(nextMode);
      const nextBatchId = generateBatchId();
      setImportBatchId(nextBatchId);
      setSnapshots([]);
      setSelectedSnapshotId(null);
      setColumnMapping(data.column_mapping ?? null);
      setPreviewSummary(data.summary ?? null);
      setOcrPreview(data.ocr ?? null);
      setOcrTextDraft(data.ocr?.text ?? "");
      setMessage("Preview ready. Review and confirm import.");
    } catch (err: any) {
      setMessage(err.message ?? "Error previewing aircraft.");
      setPreviewId(null);
      setPreviewTotalRows(0);
      setPreviewMode("client");
      setPreviewRows([]);
      setPreviewRowOverrides({});
    } finally {
      setPreviewLoading(false);
    }
  };

  const createPreviewDatasource = useCallback(
    () => ({
      getRows: async (params: {
        startRow: number;
        endRow: number;
        successCallback: (rows: PreviewRow[], lastRow?: number) => void;
        failCallback: () => void;
      }) => {
        if (!previewId) {
          params.successCallback([], 0);
          return;
        }
        const startRow = params.startRow ?? 0;
        const endRow = params.endRow ?? startRow + 200;
        const limit = Math.max(1, endRow - startRow);
        try {
          const res = await fetch(
            `${API_BASE}/aircraft/import/preview/${encodeURIComponent(
              previewId
            )}/rows?offset=${startRow}&limit=${limit}`
          );
          const data = await res.json();
          if (!res.ok) {
            throw new Error(data.detail ?? "Failed to fetch preview rows.");
          }
          const rows: PreviewRow[] = (data.rows ?? [])
            .map((row: PreviewRow) => normalizePreviewRow(row))
            .map((row: PreviewRow) => mergePreviewOverride(row));
          const totalRows = data.total_rows ?? 0;
          params.successCallback(rows, totalRows);
        } catch (err) {
          params.failCallback();
        }
      },
    }),
    [previewId, previewRowOverrides]
  );

  useEffect(() => {
    if (previewMode === "server" && previewGridApi) {
      previewGridApi.setGridOption("datasource", createPreviewDatasource());
    }
  }, [previewMode, previewGridApi, createPreviewDatasource]);

  const handlePreviewGridReady = useCallback(
    (params: GridReadyEvent) => {
      setPreviewGridApi(params.api);
      if (previewMode === "server") {
        params.api.setGridOption("datasource", createPreviewDatasource());
      }
    },
    [previewMode, createPreviewDatasource]
  );

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
    setAircraftImportComplete(false);
    await submitPreviewFile(aircraftFile);
  };

  const loadSnapshotHistory = async (batchId: string | null) => {
    if (!batchId) {
      return;
    }
    setSnapshotLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/aircraft/import/snapshots?batch_id=${encodeURIComponent(
          batchId
        )}`
      );
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail ?? "Failed to load snapshots.");
      }
      setSnapshots(data ?? []);
      setSelectedSnapshotId((data?.[0]?.id as number | undefined) ?? null);
    } catch (err: any) {
      setMessage(err.message ?? "Error loading snapshots.");
    } finally {
      setSnapshotLoading(false);
    }
  };

  useEffect(() => {
    if (importBatchId) {
      loadSnapshotHistory(importBatchId);
    }
  }, [importBatchId]);

  const parseComponentsFile = async () => {
    if (!componentsFile) {
      setMessage("Select a component file first.");
      return;
    }
    setComponentImportComplete(false);
    await submitComponentPreviewFile(componentsFile);
  };

  const reparseOcrText = async () => {
    if (!ocrTextDraft.trim()) {
      setMessage("Add corrected OCR text before re-parsing.");
      return;
    }
    setAircraftImportComplete(false);
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

  const generateBatchId = () => {
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
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

  const formulaFieldMapping = useMemo(() => {
    const mapping = new Map<string, AircraftRowField>();
    if (!columnMapping) {
      return mapping;
    }
    (Object.entries(columnMapping) as [AircraftRowField, string | null][]).forEach(
      ([field, columnName]) => {
        if (!columnName) {
          return;
        }
        mapping.set(normalizeHeader(columnName), field);
      }
    );
    return mapping;
  }, [columnMapping]);

  const getFormulaProposalForField = (
    row: PreviewRow,
    field: AircraftRowField
  ) => {
    const proposals = row.formula_proposals ?? [];
    return proposals.find(
      (proposal) => {
        const normalized = normalizeHeader(proposal.column_name);
        const mappedField = formulaFieldMapping.get(normalized);
        if (mappedField) {
          return mappedField === field;
        }
        return normalized === normalizeHeader(field);
      }
    );
  };

  const applyFormulaDecision = (
    rowNumber: number,
    field: AircraftRowField,
    decision: FormulaDecision,
    value: any,
    rowContext?: PreviewRow
  ) => {
    updatePreviewRowValue(
      rowNumber,
      field,
      value ?? "",
      "user",
      decision,
      rowContext
    );
  };

  const buildFormulaDecision = (
    row: PreviewRow,
    field: AircraftRowField
  ): FormulaDecision | undefined => {
    const proposal = getFormulaProposalForField(row, field);
    if (!proposal) {
      return undefined;
    }
    const existing = row.formula_decisions?.[field];
    if (existing) {
      return existing;
    }
    const original = normalizeValue(row.original_data?.[field]);
    const proposed = normalizeValue(proposal.proposed_value);
    const finalValue = normalizeValue(row.data[field]);
    if (finalValue === proposed) {
      return "accept";
    }
    if (finalValue === original) {
      return "keep";
    }
    return "override";
  };

  const renderFormulaCell =
    (field: AircraftRowField) =>
    (params: ICellRendererParams<PreviewRow>) => {
      const row = params.data;
      if (!row) {
        return null;
      }
      const proposal = getFormulaProposalForField(row, field);
      if (!proposal) {
        return <span>{normalizeValue(row.data[field])}</span>;
      }
      const uploadedValue = row.original_data?.[field];
      const currentValue = row.data[field];
      const proposedValue = proposal.proposed_value;
      const delta =
        typeof uploadedValue === "number" && typeof proposedValue === "number"
          ? proposedValue - uploadedValue
          : Number.isFinite(Number(proposedValue)) &&
            Number.isFinite(Number(uploadedValue))
          ? Number(proposedValue) - Number(uploadedValue)
          : null;
      const decision = buildFormulaDecision(row, field);
      const withinTolerance =
        delta !== null && Math.abs(delta) <= FORMULA_TOLERANCE;
      return (
        <div className="flex flex-col gap-1 text-xs">
          <div className="flex flex-wrap items-center gap-1">
            <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-amber-200">
              Formula mismatch
            </span>
            {decision && (
              <span className="rounded-full bg-slate-700 px-2 py-0.5 text-slate-200">
                Decision: {decision}
              </span>
            )}
          </div>
          <div className="text-slate-100">
            Uploaded: {normalizeValue(uploadedValue) || "—"}
          </div>
          <div className="text-sky-300">
            Recalc: {normalizeValue(proposedValue) || "—"}
          </div>
          {normalizeValue(currentValue) !== normalizeValue(uploadedValue) &&
            normalizeValue(currentValue) !== normalizeValue(proposedValue) && (
              <div className="text-fuchsia-200">
                Final: {normalizeValue(currentValue) || "—"}
              </div>
            )}
          <div
            className={`text-xs ${
              withinTolerance ? "text-amber-200" : "text-rose-200"
            }`}
          >
            Δ{" "}
            {delta === null
              ? "n/a"
              : `${delta > 0 ? "+" : ""}${delta.toFixed(2)}`}{" "}
            <span className="text-slate-400">(tol ±{FORMULA_TOLERANCE})</span>
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            <button
              type="button"
              className="rounded-full bg-sky-500/20 px-2 py-0.5 text-sky-200"
              onClick={() =>
                applyFormulaDecision(
                  row.row_number,
                  field,
                  "accept",
                  proposedValue,
                  params.data ?? undefined
                )
              }
            >
              Accept
            </button>
            <button
              type="button"
              className="rounded-full bg-slate-700 px-2 py-0.5 text-slate-200"
              onClick={() =>
                applyFormulaDecision(
                  row.row_number,
                  field,
                  "keep",
                  row.original_data?.[field] ?? "",
                  params.data ?? undefined
                )
              }
            >
              Keep
            </button>
            <button
              type="button"
              className="rounded-full bg-fuchsia-500/20 px-2 py-0.5 text-fuchsia-200"
              onClick={() => {
                const colId = params.column?.getColId();
                if (!colId) {
                  return;
                }
                params.api.startEditingCell({
                  rowIndex: params.node?.rowIndex ?? 0,
                  colKey: colId,
                });
              }}
            >
              Override
            </button>
          </div>
        </div>
      );
    };

  const applyTemplateToPreview = () => {
    if (previewMode === "server") {
      setMessage(
        "Template defaults are disabled in large preview mode. Apply defaults in the source file instead."
      );
      return;
    }
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
        const defaults =
          (selected.default_values ?? {}) as Partial<AircraftRowData>;
        const proposedFields = new Set(row.proposed_fields ?? []);

        if (selected.aircraft_template && !nextData.template?.trim()) {
          nextData.template = selected.aircraft_template;
        }
        if (selected.model_code && !nextData.aircraft_model_code?.trim()) {
          nextData.aircraft_model_code = selected.model_code;
        }
        if (selected.operator_code && !nextData.operator_code?.trim()) {
          nextData.operator_code = selected.operator_code;
        }

        (Object.keys(defaults) as AircraftRowField[]).forEach((key) => {
          const value = defaults[key];
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
        });

        AIRCRAFT_DIFF_FIELDS.forEach((field) => {
          if (
            normalizeValue(row.data[field]) === "" &&
            normalizeValue(nextData[field]) !== ""
          ) {
            proposedFields.add(field);
          }
        });

        const errors = validateRow(nextData);
        return {
          ...row,
          data: nextData,
          errors,
          approved: errors.length === 0 && row.approved,
          proposed_fields: Array.from(proposedFields),
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

  const aircraftGridColumns = useMemo<ColDef<PreviewRow>[]>(
    () => [
      {
        headerName: "Approve",
        colId: "approved",
        width: 110,
        pinned: "left",
        suppressMovable: true,
        cellRenderer: (params: ICellRendererParams<PreviewRow>) => {
          if (!params.data) {
            return null;
          }
          return (
            <input
              type="checkbox"
              checked={params.data.approved}
              disabled={hasErrors(params.data)}
              onChange={() => {
                const currentRow = params.data!;
                const nextRow = {
                  ...currentRow,
                  approved: !currentRow.approved,
                };
                if (previewMode === "server") {
                  params.node?.setData(nextRow);
                }
                toggleApproval(currentRow);
              }}
            />
          );
        },
      },
      {
        headerName: "Row",
        field: "row_number",
        width: 80,
        pinned: "left",
      },
      {
        headerName: "Action",
        colId: "action",
        minWidth: 200,
        cellRenderer: (params: ICellRendererParams<PreviewRow>) => {
          const row = params.data;
          if (!row) {
            return null;
          }
          const action = row.errors.length > 0 ? "invalid" : row.action;
          return (
            <div className="flex flex-col gap-1 text-xs">
              <span
                className={`inline-flex w-fit items-center rounded-full px-2 py-1 text-xs font-semibold ${
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
                <div className="text-rose-300">{row.errors.join(" ")}</div>
              )}
              {row.warnings.length > 0 && (
                <div className="text-amber-200">{row.warnings.join(" ")}</div>
              )}
            </div>
          );
        },
      },
      {
        headerName: "Diff",
        colId: "diff",
        minWidth: 220,
        cellRenderer: (params: ICellRendererParams<PreviewRow>) => {
          const row = params.data;
          if (!row) {
            return null;
          }
          const overrides = row.user_overrides ?? [];
          const proposed = (row.proposed_fields ?? []).filter(
            (field) =>
              !overrides.includes(field) &&
              normalizeValue(row.data[field]) !==
                normalizeValue(row.original_data?.[field])
          );
          const formatLabels = (fields: AircraftRowField[]) =>
            fields
              .map((field) => AIRCRAFT_FIELD_LABELS[field] ?? field)
              .join(", ");
          return (
            <div className="flex flex-col gap-1 text-xs">
              {proposed.length > 0 && (
                <div className="text-sky-300">
                  Proposed: {formatLabels(proposed)}
                </div>
              )}
              {overrides.length > 0 && (
                <div className="text-fuchsia-300">
                  Overrides: {formatLabels(overrides)}
                </div>
              )}
              {proposed.length === 0 && overrides.length === 0 && (
                <span className="text-slate-500">—</span>
              )}
            </div>
          );
        },
      },
      {
        headerName: "Serial",
        colId: "serial_number",
        editable: true,
        width: 150,
        cellRenderer: renderFormulaCell("serial_number"),
        valueGetter: (params) => params.data?.data.serial_number ?? "",
        valueSetter: (params) => {
          if (!params.data) {
            return false;
          }
          params.data.data = {
            ...params.data.data,
            serial_number: params.newValue ?? "",
          };
          return true;
        },
      },
      {
        headerName: "Registration",
        colId: "registration",
        editable: true,
        width: 150,
        cellRenderer: renderFormulaCell("registration"),
        valueGetter: (params) => params.data?.data.registration ?? "",
        valueSetter: (params) => {
          if (!params.data) {
            return false;
          }
          params.data.data = {
            ...params.data.data,
            registration: params.newValue ?? "",
          };
          return true;
        },
      },
      {
        headerName: "Template",
        colId: "template",
        editable: true,
        width: 160,
        cellRenderer: renderFormulaCell("template"),
        valueGetter: (params) => params.data?.data.template ?? "",
        valueSetter: (params) => {
          if (!params.data) {
            return false;
          }
          params.data.data = {
            ...params.data.data,
            template: params.newValue ?? "",
          };
          return true;
        },
      },
      {
        headerName: "Suggested Template",
        colId: "suggested_template",
        minWidth: 220,
        valueGetter: (params) => params.data?.suggested_template?.name ?? "—",
        cellRenderer: (params: ICellRendererParams<PreviewRow>) => {
          const suggested = params.data?.suggested_template;
          if (!suggested) {
            return <span className="text-slate-500">—</span>;
          }
          return (
            <div className="text-xs">
              <div className="font-semibold text-slate-100">
                {suggested.name}
              </div>
              {(suggested.aircraft_template ||
                suggested.model_code ||
                suggested.operator_code) && (
                <div className="text-slate-400">
                  {[
                    suggested.aircraft_template,
                    suggested.model_code,
                    suggested.operator_code,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </div>
              )}
            </div>
          );
        },
      },
      {
        headerName: "Make",
        colId: "make",
        editable: true,
        width: 140,
        cellRenderer: renderFormulaCell("make"),
        valueGetter: (params) => params.data?.data.make ?? "",
        valueSetter: (params) => {
          if (!params.data) {
            return false;
          }
          params.data.data = {
            ...params.data.data,
            make: params.newValue ?? "",
          };
          return true;
        },
      },
      {
        headerName: "Model",
        colId: "model",
        editable: true,
        width: 140,
        cellRenderer: renderFormulaCell("model"),
        valueGetter: (params) => params.data?.data.model ?? "",
        valueSetter: (params) => {
          if (!params.data) {
            return false;
          }
          params.data.data = {
            ...params.data.data,
            model: params.newValue ?? "",
          };
          return true;
        },
      },
      {
        headerName: "Base",
        colId: "home_base",
        editable: true,
        width: 140,
        cellRenderer: renderFormulaCell("home_base"),
        valueGetter: (params) => params.data?.data.home_base ?? "",
        valueSetter: (params) => {
          if (!params.data) {
            return false;
          }
          params.data.data = {
            ...params.data.data,
            home_base: params.newValue ?? "",
          };
          return true;
        },
      },
      {
        headerName: "Owner",
        colId: "owner",
        editable: true,
        width: 160,
        cellRenderer: renderFormulaCell("owner"),
        valueGetter: (params) => params.data?.data.owner ?? "",
        valueSetter: (params) => {
          if (!params.data) {
            return false;
          }
          params.data.data = {
            ...params.data.data,
            owner: params.newValue ?? "",
          };
          return true;
        },
      },
      {
        headerName: "Hours",
        colId: "total_hours",
        editable: true,
        width: 120,
        cellRenderer: renderFormulaCell("total_hours"),
        valueGetter: (params) => params.data?.data.total_hours ?? "",
        valueSetter: (params) => {
          if (!params.data) {
            return false;
          }
          params.data.data = {
            ...params.data.data,
            total_hours: params.newValue ?? "",
          };
          return true;
        },
      },
      {
        headerName: "Cycles",
        colId: "total_cycles",
        editable: true,
        width: 120,
        cellRenderer: renderFormulaCell("total_cycles"),
        valueGetter: (params) => params.data?.data.total_cycles ?? "",
        valueSetter: (params) => {
          if (!params.data) {
            return false;
          }
          params.data.data = {
            ...params.data.data,
            total_cycles: params.newValue ?? "",
          };
          return true;
        },
      },
      {
        headerName: "Last Log Date",
        colId: "last_log_date",
        editable: true,
        width: 160,
        cellRenderer: renderFormulaCell("last_log_date"),
        valueGetter: (params) => params.data?.data.last_log_date ?? "",
        valueSetter: (params) => {
          if (!params.data) {
            return false;
          }
          params.data.data = {
            ...params.data.data,
            last_log_date: params.newValue ?? "",
          };
          return true;
        },
      },
    ],
    [
      previewMode,
      renderFormulaCell,
      toggleApproval,
      hasErrors,
    ]
  );

  const aircraftGridDefaultColDef = useMemo<ColDef<PreviewRow>>(
    () => ({
      editable: false,
      resizable: true,
      sortable: true,
      suppressMovable: false,
      filter: true,
    }),
    []
  );

  const handleAircraftCellValueChanged = (
    event: CellValueChangedEvent<PreviewRow>
  ) => {
    if (!event.data) {
      return;
    }
    const field = event.colDef.colId as AircraftRowField | undefined;
    if (!field || !AIRCRAFT_DIFF_FIELDS.includes(field)) {
      return;
    }
    const decision = getFormulaProposalForField(event.data, field)
      ? "override"
      : undefined;
    updatePreviewRowValue(
      event.data.row_number,
      field,
      event.newValue ?? "",
      "user",
      decision,
      event.data
    );
  };

  const buildConfirmedRows = (rows: PreviewRow[]): ConfirmedRow[] => {
    return rows.map((row) => {
      const cells: Record<string, ConfirmedCell> = {};
      (Object.keys(row.data) as AircraftRowField[]).forEach((field) => {
        const original = row.original_data?.[field] ?? null;
        const proposal = getFormulaProposalForField(row, field);
        const proposed = proposal
          ? proposal.proposed_value
          : row.proposed_fields?.includes(field)
          ? row.data[field]
          : original;
        cells[field] = {
          original,
          proposed,
          final: row.data[field],
          decision: buildFormulaDecision(row, field),
        };
      });
      return { row_number: row.row_number, cells };
    });
  };

  const confirmImport = async () => {
    const approvedRows =
      previewMode === "client"
        ? previewRows.filter((row) => row.approved && row.errors.length === 0)
        : [];
    const overrideRows = Object.values(previewRowOverrides);
    const approvedOverrideRows = overrideRows.filter(
      (row) => row.approved && row.errors.length === 0
    );
    const rejectedOverrideRows = overrideRows.filter((row) => !row.approved);
    if (
      previewMode === "client" &&
      approvedRows.length === 0 &&
      approvedOverrideRows.length === 0
    ) {
      setMessage("Select at least one valid row to import.");
      return;
    }
    if (
      previewMode === "server" &&
      !previewSummary?.new &&
      !previewSummary?.update &&
      approvedOverrideRows.length === 0
    ) {
      setMessage("Select at least one valid row to import.");
      return;
    }
    setConfirmLoading(true);
    setMessage(null);

    try {
      const approvedRowNumbers =
        previewMode === "client"
          ? approvedRows.map((row) => row.row_number)
          : approvedOverrideRows.map((row) => row.row_number);
      const rejectedRowNumbers =
        previewMode === "server"
          ? rejectedOverrideRows.map((row) => row.row_number)
          : [];
      const res = await fetch(`${API_BASE}/aircraft/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rows:
            previewMode === "client"
              ? approvedRows.map((row) => ({
                  row_number: row.row_number,
                  ...row.data,
                }))
              : [],
          preview_id: previewId,
          approved_row_numbers:
            previewMode === "server" ? approvedRowNumbers : undefined,
          rejected_row_numbers:
            previewMode === "server" ? rejectedRowNumbers : undefined,
          confirmed_rows:
            previewMode === "client"
              ? buildConfirmedRows(approvedRows)
              : buildConfirmedRows(approvedOverrideRows),
          batch_id: importBatchId,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail ?? "Import failed");
      }
      setImportBatchId(data.batch_id ?? importBatchId);
      await loadSnapshotHistory(data.batch_id ?? importBatchId);
      setMessage(
        `Aircraft import OK. Created: ${data.created}, Updated: ${data.updated}`
      );
      setAircraftImportComplete(true);
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
      setComponentImportComplete(true);
    } catch (err: any) {
      setMessage(err.message ?? "Error importing components.");
    } finally {
      setComponentConfirmLoading(false);
    }
  };

  const approvedCount = useMemo(() => {
    if (previewMode === "client") {
      return previewRows.filter((row) => row.approved && !hasErrors(row))
        .length;
    }
    const baseApproved =
      (previewSummary?.new ?? 0) + (previewSummary?.update ?? 0);
    const overrides = Object.values(previewRowOverrides);
    const rejected = overrides.filter(
      (row) => !row.approved && row.errors.length === 0
    ).length;
    const added = overrides.filter(
      (row) => row.approved && row.errors.length === 0 && row.action === "invalid"
    ).length;
    return Math.max(0, baseApproved - rejected + added);
  }, [previewMode, previewRows, previewSummary, previewRowOverrides]);

  const componentApprovedCount = useMemo(
    () =>
      componentPreviewRows.filter(
        (row) => row.approved && !hasComponentErrors(row)
      ).length,
    [componentPreviewRows]
  );

  const aircraftHasPreview =
    previewRows.length > 0 || previewTotalRows > 0 || !!previewId;
  const componentHasPreview = componentPreviewRows.length > 0;

  const aircraftStep = aircraftImportComplete
    ? 3
    : aircraftHasPreview
    ? 2
    : aircraftFile
    ? 1
    : 0;
  const componentStep = componentImportComplete
    ? 3
    : componentHasPreview
    ? 2
    : componentsFile
    ? 1
    : 0;

  const aircraftProgress = Math.round((aircraftStep / 3) * 100);
  const componentProgress = Math.round((componentStep / 3) * 100);

  const handleUndoSnapshot = async () => {
    if (!selectedSnapshotId) {
      setMessage("Select a snapshot to undo.");
      return;
    }
    setSnapshotActionLoading(true);
    setMessage(null);
    try {
      const res = await fetch(
        `${API_BASE}/aircraft/import/snapshots/${selectedSnapshotId}/restore`,
        { method: "POST" }
      );
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail ?? "Failed to restore snapshot.");
      }
      await loadSnapshotHistory(data.batch_id ?? importBatchId);
      setMessage(`Snapshot restored. Rows updated: ${data.restored ?? 0}.`);
    } catch (err: any) {
      setMessage(err.message ?? "Error restoring snapshot.");
    } finally {
      setSnapshotActionLoading(false);
    }
  };

  const handleRedoSnapshot = async () => {
    if (!selectedSnapshotId) {
      setMessage("Select a snapshot to reapply.");
      return;
    }
    setSnapshotActionLoading(true);
    setMessage(null);
    try {
      const res = await fetch(
        `${API_BASE}/aircraft/import/snapshots/${selectedSnapshotId}/reapply`,
        { method: "POST" }
      );
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail ?? "Failed to reapply snapshot.");
      }
      await loadSnapshotHistory(data.batch_id ?? importBatchId);
      setMessage(`Snapshot reapplied. Rows updated: ${data.reapplied ?? 0}.`);
    } catch (err: any) {
      setMessage(err.message ?? "Error reapplying snapshot.");
    } finally {
      setSnapshotActionLoading(false);
    }
  };

  return (
    <div className="page-layout">
      <div className="page-header">
        <h1 className="page-header__title">Aircraft Loader / Setup</h1>
        <p className="page-header__subtitle">
          Follow the guided steps to upload aircraft masters, review the preview,
          and confirm updates. The progress bar shows where you are in the
          process.
        </p>
      </div>

      {userIsSuperuser && (
        <section className="page-section">
          <h2 className="page-section__title">Target AMO</h2>
          <p className="page-section__body">
            Select the AMO you are configuring. This is only available to
            platform superusers.
          </p>
          <div className="page-section__grid">
            <div className="form-row">
              <label htmlFor="amo-target">AMO</label>
              <select
                id="amo-target"
                className="input"
                value={selectedAmoId}
                onChange={handleAmoChange}
                disabled={amoLoading || amoOptions.length === 0}
              >
                <option value="">
                  {amoLoading ? "Loading AMOs..." : "Select AMO"}
                </option>
                {amoOptions.map((amo) => (
                  <option key={amo.id} value={amo.id}>
                    {amo.amo_code} · {amo.name}
                  </option>
                ))}
              </select>
              {amoError && <div className="alert alert-error">{amoError}</div>}
            </div>
          </div>
        </section>
      )}

      {/* AIRCRAFT MASTER IMPORT */}
      <section className="page-section">
        <h2 className="page-section__title">1. Import Aircraft Master List</h2>
        <p className="page-section__body">
          Upload a CSV/Excel file containing aircraft serials, registration,
          type, base, hours, and cycles. You can preview and approve rows before
          final import.
        </p>

        <div className="import-progress">
          <div className="import-progress__summary">
            <span>Aircraft master progress</span>
            <span>{aircraftProgress}%</span>
          </div>
          <div
            className={`import-progress__bar ${
              previewLoading || confirmLoading ? "is-loading" : ""
            }`}
          >
            <span style={{ width: `${aircraftProgress}%` }} />
          </div>
          <ol className="import-stepper">
            <li className={aircraftStep >= 1 ? "is-complete" : ""}>
              Upload file
            </li>
            <li className={aircraftStep >= 2 ? "is-complete" : ""}>
              Review preview
            </li>
            <li className={aircraftStep >= 3 ? "is-complete" : ""}>
              Confirm import
            </li>
          </ol>
        </div>

        <div className="page-section__grid">
          <div className="card card--form">
            <div className="card-header">
              <div>
                <div className="import-step__eyebrow">Step 1</div>
                <h3 className="import-step__title">Upload aircraft file</h3>
              </div>
              <span className="import-step__status">
                {aircraftStep >= 1 ? "Ready" : "Waiting"}
              </span>
            </div>

            <div className="form-row">
              <label htmlFor="aircraft-file">Aircraft master file</label>
              <input
                id="aircraft-file"
                type="file"
                accept=".csv,.txt,.xlsx,.xlsm,.xls,.pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp"
                onChange={handleAircraftFileChange}
                className="input"
              />
              <p className="form-hint">
                Accepted formats: CSV, XLSX, PDF, or image scans (OCR supported).
              </p>
            </div>

            <div className="form-actions form-actions--inline">
              <button
                onClick={parseAircraftFile}
                disabled={previewLoading}
                className="btn"
              >
                {previewLoading ? "Parsing..." : "Parse & Preview"}
              </button>
            </div>
          </div>

          <div className="card card--form">
            <div className="card-header">
              <div>
                <div className="import-step__eyebrow">Step 2</div>
                <h3 className="import-step__title">Review & map data</h3>
              </div>
              <span className="import-step__status">
                {aircraftStep >= 2 ? "Ready" : "Waiting"}
              </span>
            </div>

            {previewSummary && (
              <div className="import-summary-grid">
                <div className="card card--success">
                  <div className="import-summary__label">New</div>
                  <div className="import-summary__value">
                    {previewSummary.new}
                  </div>
                </div>
                <div className="card card--info">
                  <div className="import-summary__label">Update</div>
                  <div className="import-summary__value">
                    {previewSummary.update}
                  </div>
                </div>
                <div className="card card--warning">
                  <div className="import-summary__label">Invalid</div>
                  <div className="import-summary__value">
                    {previewSummary.invalid}
                  </div>
                </div>
              </div>
            )}

            {(previewRows.length > 0 || previewTotalRows > 0) && (
              <div className="table-wrapper import-grid">
                <div
                  className="ag-theme-alpine"
                  style={{ height: 520, minWidth: 720 }}
                >
                  <AgGridReact<PreviewRow>
                    key={previewMode}
                    rowData={previewMode === "client" ? previewRows : undefined}
                    columnDefs={aircraftGridColumns}
                    defaultColDef={aircraftGridDefaultColDef}
                    rowSelection="multiple"
                    suppressRowClickSelection
                    rowBuffer={12}
                    rowModelType={
                      previewMode === "server" ? "infinite" : "clientSide"
                    }
                    cacheBlockSize={200}
                    maxBlocksInCache={5}
                    suppressColumnVirtualisation={false}
                    suppressRowVirtualisation={false}
                    enableCellTextSelection
                    enableRangeSelection
                    getRowId={(params) => `${params.data.row_number}`}
                    onGridReady={handlePreviewGridReady}
                    onCellValueChanged={handleAircraftCellValueChanged}
                  />
                </div>
              </div>
            )}

            {columnMapping && (
              <div className="form-hint">
                Detected mapping:{" "}
                {Object.entries(columnMapping)
                  .filter(([, value]) => value)
                  .map(([key, value]) => `${key} → ${value}`)
                  .join(", ")}
              </div>
            )}

            <details className="import-advanced" open={false}>
              <summary>Templates & defaults</summary>
              <div className="import-advanced__body">
                <div className="form-row">
                  <label>Template</label>
                  <select
                    value={selectedTemplateId}
                    onChange={(e) =>
                      setSelectedTemplateId(
                        e.target.value ? Number(e.target.value) : ""
                      )
                    }
                    className="input"
                  >
                    <option value="">Select template</option>
                    {templates.map((template) => (
                      <option key={template.id} value={template.id}>
                        {template.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-actions form-actions--inline">
                  <button
                    onClick={applyTemplateToPreview}
                    disabled={
                      previewMode === "server" ||
                      !previewRows.length ||
                      !selectedTemplateId
                    }
                    className="btn"
                  >
                    Apply template to preview
                  </button>
                  <button
                    onClick={saveMappingTemplate}
                    disabled={templateLoading || !columnMapping}
                    className="btn-secondary"
                  >
                    {templateLoading ? "Saving..." : "Save mapping template"}
                  </button>
                </div>

                <div className="import-template-grid">
                  <div className="form-row">
                    <label>Template name</label>
                    <input
                      type="text"
                      value={templateName}
                      onChange={(e) => setTemplateName(e.target.value)}
                      className="input"
                    />
                  </div>
                  <div className="form-row">
                    <label>Aircraft template</label>
                    <input
                      type="text"
                      value={templateAircraftTemplate}
                      onChange={(e) =>
                        setTemplateAircraftTemplate(e.target.value)
                      }
                      className="input"
                    />
                  </div>
                  <div className="form-row">
                    <label>Model code</label>
                    <input
                      type="text"
                      value={templateModelCode}
                      onChange={(e) => setTemplateModelCode(e.target.value)}
                      className="input"
                    />
                  </div>
                  <div className="form-row">
                    <label>Operator code</label>
                    <input
                      type="text"
                      value={templateOperatorCode}
                      onChange={(e) => setTemplateOperatorCode(e.target.value)}
                      className="input"
                    />
                  </div>
                </div>

                <div className="form-row">
                  <label>Default values (JSON)</label>
                  <textarea
                    value={templateDefaultsJson}
                    onChange={(e) => setTemplateDefaultsJson(e.target.value)}
                    rows={4}
                    className="input"
                  />
                </div>
              </div>
            </details>

            {ocrPreview && (
              <details className="import-advanced" open={false}>
                <summary>OCR preview details</summary>
                <div className="import-advanced__body">
                  <div className="import-ocr__header">
                    <div>
                      <div className="import-ocr__title">OCR Preview</div>
                      <div className="form-hint">
                        {ocrPreview.file_type
                          ? `Detected ${ocrPreview.file_type.toUpperCase()}`
                          : "Detected OCR content"}
                      </div>
                    </div>
                    <div className="import-ocr__confidence">
                      Confidence:{" "}
                      <strong>
                        {ocrPreview.confidence !== null &&
                        ocrPreview.confidence !== undefined
                          ? `${ocrPreview.confidence.toFixed(1)}%`
                          : "n/a"}
                      </strong>
                    </div>
                  </div>

                  {ocrPreview.samples && ocrPreview.samples.length > 0 && (
                    <div className="import-ocr__samples">
                      <div className="import-ocr__label">Extracted samples</div>
                      <ul>
                        {ocrPreview.samples.map((sample, index) => (
                          <li key={`${sample}-${index}`}>{sample}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <div className="form-row">
                    <label>OCR text (edit before re-parsing)</label>
                    <textarea
                      value={ocrTextDraft}
                      onChange={(e) => setOcrTextDraft(e.target.value)}
                      rows={6}
                      className="input import-ocr__textarea"
                    />
                    <p className="form-hint">
                      Re-parsing expects CSV/TSV-style rows with a header line.
                    </p>
                  </div>

                  <div className="form-actions form-actions--inline">
                    <button
                      onClick={reparseOcrText}
                      disabled={previewLoading}
                      className="btn"
                    >
                      {previewLoading
                        ? "Re-parsing..."
                        : "Rebuild Preview from OCR"}
                    </button>
                  </div>
                </div>
              </details>
            )}
          </div>

          <div className="card card--form">
            <div className="card-header">
              <div>
                <div className="import-step__eyebrow">Step 3</div>
                <h3 className="import-step__title">Confirm & finalize</h3>
              </div>
              <span className="import-step__status">
                {aircraftStep >= 3 ? "Complete" : "Waiting"}
              </span>
            </div>

            <div className="form-actions form-actions--inline">
              <button
                onClick={confirmImport}
                disabled={confirmLoading || approvedCount === 0}
                className="btn"
              >
                {confirmLoading
                  ? "Importing..."
                  : `Confirm Import (${approvedCount})`}
              </button>
            </div>

            <div className="import-snapshot">
              <div className="import-snapshot__header">
                <div>
                  <h4>Undo / Redo</h4>
                  <p>Snapshot history for this import batch.</p>
                </div>
                <button
                  onClick={() => loadSnapshotHistory(importBatchId)}
                  disabled={!importBatchId || snapshotLoading}
                  className="btn-secondary"
                >
                  {snapshotLoading ? "Refreshing..." : "Refresh"}
                </button>
              </div>

              <div className="import-snapshot__controls">
                <select
                  value={selectedSnapshotId ?? ""}
                  onChange={(event) =>
                    setSelectedSnapshotId(
                      event.target.value ? Number(event.target.value) : null
                    )
                  }
                  disabled={!snapshots.length}
                  className="input"
                >
                  <option value="">Select snapshot...</option>
                  {snapshots.map((snapshot) => (
                    <option key={snapshot.id} value={snapshot.id}>
                      {new Date(snapshot.created_at).toLocaleString()} (#
                      {snapshot.id})
                    </option>
                  ))}
                </select>
                <div className="import-snapshot__actions">
                  <button
                    onClick={handleUndoSnapshot}
                    disabled={
                      snapshotActionLoading ||
                      !selectedSnapshotId ||
                      !snapshots.length
                    }
                    className="btn-secondary"
                  >
                    Undo
                  </button>
                  <button
                    onClick={handleRedoSnapshot}
                    disabled={
                      snapshotActionLoading ||
                      !selectedSnapshotId ||
                      !snapshots.length
                    }
                    className="btn-secondary"
                  >
                    Redo
                  </button>
                </div>
              </div>
              {importBatchId && (
                <p className="form-hint">Batch ID: {importBatchId}</p>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* COMPONENT IMPORT */}
      <section className="page-section">
        <h2 className="page-section__title">
          2. Import Components for One Aircraft
        </h2>
        <p className="page-section__body">
          Upload components for one aircraft at a time, then review and confirm
          before committing.
        </p>

        <div className="import-progress">
          <div className="import-progress__summary">
            <span>Component import progress</span>
            <span>{componentProgress}%</span>
          </div>
          <div
            className={`import-progress__bar ${
              componentPreviewLoading || componentConfirmLoading
                ? "is-loading"
                : ""
            }`}
          >
            <span style={{ width: `${componentProgress}%` }} />
          </div>
          <ol className="import-stepper">
            <li className={componentStep >= 1 ? "is-complete" : ""}>
              Upload file
            </li>
            <li className={componentStep >= 2 ? "is-complete" : ""}>
              Review preview
            </li>
            <li className={componentStep >= 3 ? "is-complete" : ""}>
              Confirm import
            </li>
          </ol>
        </div>

        <div className="page-section__grid">
          <div className="card card--form">
            <div className="card-header">
              <div>
                <div className="import-step__eyebrow">Step 1</div>
                <h3 className="import-step__title">
                  Identify the aircraft & upload
                </h3>
              </div>
              <span className="import-step__status">
                {componentStep >= 1 ? "Ready" : "Waiting"}
              </span>
            </div>

            <div className="import-template-grid">
              <div className="form-row">
                <label>Aircraft serial number</label>
                <input
                  type="text"
                  value={componentAircraftSerial}
                  onChange={(e) => setComponentAircraftSerial(e.target.value)}
                  className="input"
                  placeholder="e.g. 574, 510, 331"
                />
              </div>
              <div className="form-row">
                <label>Components file</label>
                <input
                  type="file"
                  accept=".csv,.txt,.xlsx,.xlsm,.xls,.pdf"
                  onChange={handleComponentsFileChange}
                  className="input"
                />
                <p className="form-hint">
                  Use component positions (L ENGINE, R ENGINE, APU) and PN/SN
                  columns.
                </p>
              </div>
            </div>

            <div className="form-actions form-actions--inline">
              <button
                onClick={parseComponentsFile}
                disabled={componentPreviewLoading}
                className="btn"
              >
                {componentPreviewLoading ? "Parsing..." : "Parse & Preview"}
              </button>
            </div>
          </div>

          <div className="card card--form">
            <div className="card-header">
              <div>
                <div className="import-step__eyebrow">Step 2</div>
                <h3 className="import-step__title">Review & map components</h3>
              </div>
              <span className="import-step__status">
                {componentStep >= 2 ? "Ready" : "Waiting"}
              </span>
            </div>

            {componentSummary && (
              <div className="import-summary-grid">
                <div className="card card--success">
                  <div className="import-summary__label">New</div>
                  <div className="import-summary__value">
                    {componentSummary.new}
                  </div>
                </div>
                <div className="card card--info">
                  <div className="import-summary__label">Update</div>
                  <div className="import-summary__value">
                    {componentSummary.update}
                  </div>
                </div>
                <div className="card card--warning">
                  <div className="import-summary__label">Invalid</div>
                  <div className="import-summary__value">
                    {componentSummary.invalid}
                  </div>
                </div>
              </div>
            )}

            <details className="import-advanced" open={false}>
              <summary>Templates & defaults</summary>
              <div className="import-advanced__body">
                <div className="form-row">
                  <label>Component template</label>
                  <select
                    value={componentSelectedTemplateId}
                    onChange={(e) =>
                      setComponentSelectedTemplateId(
                        e.target.value ? Number(e.target.value) : ""
                      )
                    }
                    className="input"
                  >
                    <option value="">Select template</option>
                    {componentTemplates.map((template) => (
                      <option key={template.id} value={template.id}>
                        {template.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-actions form-actions--inline">
                  <button
                    onClick={applyComponentTemplateToPreview}
                    disabled={
                      !componentPreviewRows.length ||
                      !componentSelectedTemplateId
                    }
                    className="btn"
                  >
                    Apply template to preview
                  </button>
                  <button
                    onClick={saveComponentTemplate}
                    disabled={componentTemplateLoading || !componentColumnMapping}
                    className="btn-secondary"
                  >
                    {componentTemplateLoading
                      ? "Saving..."
                      : "Save mapping template"}
                  </button>
                </div>

                <div className="import-template-grid">
                  <div className="form-row">
                    <label>Template name</label>
                    <input
                      type="text"
                      value={componentTemplateName}
                      onChange={(e) => setComponentTemplateName(e.target.value)}
                      className="input"
                    />
                  </div>
                  <div className="form-row">
                    <label>Aircraft template</label>
                    <input
                      type="text"
                      value={componentTemplateAircraftTemplate}
                      onChange={(e) =>
                        setComponentTemplateAircraftTemplate(e.target.value)
                      }
                      className="input"
                    />
                  </div>
                  <div className="form-row">
                    <label>Model code</label>
                    <input
                      type="text"
                      value={componentTemplateModelCode}
                      onChange={(e) => setComponentTemplateModelCode(e.target.value)}
                      className="input"
                    />
                  </div>
                  <div className="form-row">
                    <label>Operator code</label>
                    <input
                      type="text"
                      value={componentTemplateOperatorCode}
                      onChange={(e) =>
                        setComponentTemplateOperatorCode(e.target.value)
                      }
                      className="input"
                    />
                  </div>
                </div>

                <div className="form-row">
                  <label>Default values (JSON)</label>
                  <textarea
                    value={componentTemplateDefaultsJson}
                    onChange={(e) =>
                      setComponentTemplateDefaultsJson(e.target.value)
                    }
                    rows={4}
                    className="input"
                  />
                </div>
              </div>
            </details>

            {componentPreviewRows.length > 0 && (
              <div className="table-wrapper import-grid">
                <table className="table table-compact table-striped">
                  <thead>
                    <tr>
                      <th>Approve</th>
                      <th>Row</th>
                      <th>Action</th>
                      <th>Position</th>
                      <th>Part Number</th>
                      <th>Serial Number</th>
                      <th>Existing PN/SN</th>
                      <th>ATA</th>
                      <th>Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {componentPreviewRows.map((row, index) => {
                      const action =
                        row.errors.length > 0 ? "invalid" : row.action;
                      const positionMissing = !row.data.position?.trim();
                      const existingPart = row.existing_component?.part_number;
                      const existingSerial =
                        row.existing_component?.serial_number;
                      const partDiff =
                        existingPart &&
                        row.data.part_number &&
                        existingPart !== row.data.part_number;
                      const serialDiff =
                        existingSerial &&
                        row.data.serial_number &&
                        existingSerial !== row.data.serial_number;
                      return (
                        <tr key={`${row.row_number}-${index}`}>
                          <td>
                            <input
                              type="checkbox"
                              checked={row.approved}
                              disabled={hasComponentErrors(row)}
                              onChange={() => toggleComponentApproval(index)}
                            />
                          </td>
                          <td className="table-secondary-text">
                            {row.row_number}
                          </td>
                          <td>
                            <span
                              className={`import-badge import-badge--${action}`}
                            >
                              {action}
                            </span>
                            {row.errors.length > 0 && (
                              <div className="import-row-warning">
                                {row.errors.join(" ")}
                              </div>
                            )}
                            {row.warnings.length > 0 && (
                              <div className="import-row-warning import-row-warning--warn">
                                {row.warnings.join(" ")}
                              </div>
                            )}
                            {row.dedupe_suggestions &&
                              row.dedupe_suggestions.length > 0 && (
                                <div className="import-row-warning import-row-warning--warn">
                                  {row.dedupe_suggestions.map(
                                    (suggestion, idx) => (
                                      <div
                                        key={`${row.row_number}-dedupe-${idx}`}
                                      >
                                        {suggestion.source === "existing"
                                          ? "Existing"
                                          : "File"}{" "}
                                        match for {suggestion.part_number}/
                                        {suggestion.serial_number}:{" "}
                                        {suggestion.positions.join(", ")}
                                      </div>
                                    )
                                  )}
                                </div>
                              )}
                          </td>
                          <td>
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
                              className={`input input--compact ${
                                positionMissing ? "input--error" : ""
                              }`}
                            />
                          </td>
                          <td>
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
                              className={`input input--compact ${
                                partDiff ? "input--warn" : ""
                              }`}
                            />
                          </td>
                          <td>
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
                              className={`input input--compact ${
                                serialDiff ? "input--warn" : ""
                              }`}
                            />
                          </td>
                          <td className="table-secondary-text">
                            {existingPart || existingSerial ? (
                              <div>
                                <div>{existingPart ?? "—"}</div>
                                <div className="table-secondary-text">
                                  {existingSerial ?? "—"}
                                </div>
                              </div>
                            ) : (
                              <span className="table-secondary-text">—</span>
                            )}
                          </td>
                          <td>
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
                              className="input input--compact"
                            />
                          </td>
                          <td>
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
                              className="input input--compact"
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
              <div className="form-hint">
                Detected mapping:{" "}
                {Object.entries(componentColumnMapping)
                  .filter(([, value]) => value)
                  .map(([key, value]) => `${key} → ${value}`)
                  .join(", ")}
              </div>
            )}
          </div>

          <div className="card card--form">
            <div className="card-header">
              <div>
                <div className="import-step__eyebrow">Step 3</div>
                <h3 className="import-step__title">Confirm component import</h3>
              </div>
              <span className="import-step__status">
                {componentStep >= 3 ? "Complete" : "Waiting"}
              </span>
            </div>
            <div className="form-actions form-actions--inline">
              <button
                onClick={confirmComponentImport}
                disabled={
                  componentConfirmLoading || componentApprovedCount === 0
                }
                className="btn"
              >
                {componentConfirmLoading
                  ? "Importing..."
                  : `Confirm Import (${componentApprovedCount})`}
              </button>
            </div>
          </div>
        </div>
      </section>

      {message && <div className="alert">{message}</div>}
    </div>
  );
};

export default AircraftImportPage;
