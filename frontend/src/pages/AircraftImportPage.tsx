// frontend/src/pages/AircraftImportPage.tsx
import React, { useMemo, useState } from "react";

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
};

const AircraftImportPage: React.FC = () => {
  const [aircraftFile, setAircraftFile] = useState<File | null>(null);
  const [componentsFile, setComponentsFile] = useState<File | null>(null);
  const [componentAircraftSerial, setComponentAircraftSerial] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [previewRows, setPreviewRows] = useState<PreviewRow[]>([]);
  const [columnMapping, setColumnMapping] = useState<
    Record<string, string | null> | null
  >(null);
  const [previewSummary, setPreviewSummary] = useState<{
    new: number;
    update: number;
    invalid: number;
  } | null>(null);

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

  const parseAircraftFile = async () => {
    if (!aircraftFile) {
      setMessage("Select an aircraft file first.");
      return;
    }
    setPreviewLoading(true);
    setMessage(null);

    const formData = new FormData();
    formData.append("file", aircraftFile);

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
      setMessage("Preview ready. Review and confirm import.");
    } catch (err: any) {
      setMessage(err.message ?? "Error previewing aircraft.");
    } finally {
      setPreviewLoading(false);
    }
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

  const uploadComponents = async () => {
    if (!componentAircraftSerial.trim()) {
      setMessage("Enter the aircraft serial number for components.");
      return;
    }
    if (!componentsFile) {
      setMessage("Select a component file first.");
      return;
    }
    setLoading(true);
    setMessage(null);

    const formData = new FormData();
    formData.append("file", componentsFile);

    try {
      const res = await fetch(
        `${API_BASE}/aircraft/${encodeURIComponent(
          componentAircraftSerial.trim()
        )}/components/import`,
        {
          method: "POST",
          body: formData,
        }
      );

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail ?? "Component import failed");
      }
      setMessage(
        `Components import OK for aircraft ${data.aircraft_serial_number}. ` +
          `New components: ${data.components_created}`
      );
    } catch (err: any) {
      setMessage(err.message ?? "Error importing components.");
    } finally {
      setLoading(false);
    }
  };

  const approvedCount = useMemo(
    () => previewRows.filter((row) => row.approved && !hasErrors(row)).length,
    [previewRows]
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
              accept=".csv,.txt,.xlsx,.xlsm,.xls,.pdf"
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

          <button
            onClick={uploadComponents}
            disabled={loading}
            className="px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 disabled:opacity-50"
          >
            {loading ? "Uploading..." : "Upload Components File"}
          </button>
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
