// src/pages/work/WorkOrderSearchPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getContext } from "../../services/auth";
import {
  createWorkOrder,
  getWorkOrderByNumber,
  listWorkOrders,
  type WorkOrderCreatePayload,
  type WorkOrderRead,
  type WorkOrderStatus,
  type WorkOrderType,
} from "../../services/workOrders";

type UrlParams = {
  amoCode?: string;
  department?: string;
};

type Filters = {
  woNumber: string;
  aircraftSerial: string;
  status: string;
  type: string;
  dateFrom: string;
  dateTo: string;
};

type CreateForm = {
  woNumber: string;
  aircraftSerial: string;
  description: string;
  checkType: string;
  woType: WorkOrderType | "";
  status: WorkOrderStatus | "";
  isScheduled: boolean;
  dueDate: string;
  openDate: string;
};

const DEFAULT_FILTERS: Filters = {
  woNumber: "",
  aircraftSerial: "",
  status: "",
  type: "",
  dateFrom: "",
  dateTo: "",
};

const DEFAULT_CREATE_FORM: CreateForm = {
  woNumber: "",
  aircraftSerial: "",
  description: "",
  checkType: "",
  woType: "PERIODIC",
  status: "DRAFT",
  isScheduled: true,
  dueDate: "",
  openDate: "",
};

const STATUS_OPTIONS: Array<{ value: WorkOrderStatus; label: string }> = [
  { value: "DRAFT", label: "Draft" },
  { value: "RELEASED", label: "Released" },
  { value: "IN_PROGRESS", label: "In progress" },
  { value: "COMPLETED", label: "Completed" },
  { value: "CANCELLED", label: "Cancelled" },
];

const TYPE_OPTIONS: Array<{ value: WorkOrderType; label: string }> = [
  { value: "PERIODIC", label: "Periodic" },
  { value: "NON_ROUTINE", label: "Non-routine" },
  { value: "DEFECT", label: "Defect" },
];

const WorkOrderSearchPage: React.FC = () => {
  const { amoCode, department } = useParams<UrlParams>();
  const context = getContext();
  const navigate = useNavigate();
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [createForm, setCreateForm] = useState<CreateForm>(DEFAULT_CREATE_FORM);
  const [results, setResults] = useState<WorkOrderRead[]>([]);
  const [selected, setSelected] = useState<WorkOrderRead | null>(null);
  const [loading, setLoading] = useState(false);
  const [createLoading, setCreateLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const resolvedAmoCode = amoCode || context.amoSlug || "system";
  const activeDepartment = (department || context.department || "planning").toLowerCase();
  const basePath = `/maintenance/${resolvedAmoCode}/${activeDepartment}`;
  const filteredResults = useMemo(() => results, [results]);

  const fetchWorkOrders = async () => {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      if (filters.woNumber.trim()) {
        const wo = await getWorkOrderByNumber(filters.woNumber.trim());
        setResults(wo ? [wo] : []);
        setSelected(wo ?? null);
        if (!wo) setNotice("No work order found for that number.");
        return;
      }

      const data = await listWorkOrders({
        aircraft_serial_number: filters.aircraftSerial || undefined,
        status: (filters.status as WorkOrderStatus) || undefined,
        wo_type: (filters.type as WorkOrderType) || undefined,
      });
      setResults(data);
      setSelected(data[0] ?? null);
      if (data.length === 0) setNotice("No work orders match these filters.");
    } catch (e: any) {
      console.error("Failed to load work orders", e);
      setError(e?.message || "Could not load work orders.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWorkOrders();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleChange = (key: keyof Filters) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setFilters((prev) => ({ ...prev, [key]: e.target.value }));
  };

  const handleCreateChange =
    (key: keyof CreateForm) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      const value =
        e.target.type === "checkbox"
          ? (e.target as HTMLInputElement).checked
          : e.target.value;
      setCreateForm((prev) => ({ ...prev, [key]: value as CreateForm[typeof key] }));
    };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchWorkOrders();
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateLoading(true);
    setError(null);
    setNotice(null);
    try {
      const payload: WorkOrderCreatePayload = {
        wo_number: createForm.woNumber.trim(),
        aircraft_serial_number: createForm.aircraftSerial.trim(),
        description: createForm.description.trim() || null,
        check_type: createForm.checkType.trim() || null,
        wo_type: createForm.woType || "PERIODIC",
        status: createForm.status || "DRAFT",
        is_scheduled: createForm.isScheduled,
        due_date: createForm.dueDate || null,
        open_date: createForm.openDate || null,
      };

      if (!payload.wo_number || !payload.aircraft_serial_number) {
        setError("WO number and aircraft serial are required.");
        return;
      }

      const created = await createWorkOrder(payload);
      setNotice(`Work order ${created.wo_number || payload.wo_number} created.`);
      setCreateForm(DEFAULT_CREATE_FORM);
      setSelected(created);
      setResults((prev) => {
        const exists = prev.some((item) => item.id === created.id);
        return exists ? prev : [created, ...prev];
      });
    } catch (e: any) {
      console.error("Failed to create work order", e);
      setError(e?.message || "Could not create work order.");
    } finally {
      setCreateLoading(false);
    }
  };

  const handleClear = () => {
    setFilters(DEFAULT_FILTERS);
    setResults([]);
    setSelected(null);
    setNotice(null);
  };

  const openWorkOrder = () => {
    if (!selected?.id) return;
    navigate(`${basePath}/work-orders/${selected.id}`);
  };

  const stubAction = (label: string) => {
    setNotice(`${label} is not available yet.`);
  };

  return (
    <DepartmentLayout amoCode={resolvedAmoCode} activeDepartment={activeDepartment}>
      <div className="page-layout page-layout--wide">
        <div className="page-header">
          <h1 className="page-header__title">Work Order Search</h1>
          <p className="page-header__subtitle">
            Filter work orders, review results, and open the selected work order.
          </p>
        </div>

        <div className="work-orders-grid">
          <form className="work-orders-panel" onSubmit={handleSubmit}>
            <h2 className="work-orders-panel__title">Filters</h2>
            <div className="form-grid">
              <label>
                WO Number
                <input
                  type="text"
                  value={filters.woNumber}
                  onChange={handleChange("woNumber")}
                  placeholder="WO-1234"
                />
              </label>
              <label>
                Aircraft Serial
                <input
                  type="text"
                  value={filters.aircraftSerial}
                  onChange={handleChange("aircraftSerial")}
                  placeholder="Serial number"
                />
              </label>
              <label>
                Status
                <select value={filters.status} onChange={handleChange("status")}>
                  <option value="">All statuses</option>
                  {STATUS_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Type
                <select value={filters.type} onChange={handleChange("type")}>
                  <option value="">All types</option>
                  {TYPE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Date From (optional)
                <input type="date" value={filters.dateFrom} onChange={handleChange("dateFrom")} />
              </label>
              <label>
                Date To (optional)
                <input type="date" value={filters.dateTo} onChange={handleChange("dateTo")} />
              </label>
            </div>
            <div className="page-section__actions">
              <button type="submit" className="btn btn-primary">
                Refresh
              </button>
              <button type="button" className="btn btn-secondary" onClick={handleClear}>
                Clear
              </button>
            </div>
          </form>

          <form className="work-orders-panel" onSubmit={handleCreateSubmit}>
            <h2 className="work-orders-panel__title">Create work order</h2>
            <div className="form-grid">
              <label>
                WO Number
                <input
                  type="text"
                  value={createForm.woNumber}
                  onChange={handleCreateChange("woNumber")}
                  placeholder="WO-1234"
                />
              </label>
              <label>
                Aircraft Serial
                <input
                  type="text"
                  value={createForm.aircraftSerial}
                  onChange={handleCreateChange("aircraftSerial")}
                  placeholder="Aircraft serial"
                />
              </label>
              <label>
                Description
                <input
                  type="text"
                  value={createForm.description}
                  onChange={handleCreateChange("description")}
                  placeholder="Brief scope"
                />
              </label>
              <label>
                Check Type
                <input
                  type="text"
                  value={createForm.checkType}
                  onChange={handleCreateChange("checkType")}
                  placeholder="A, C, 200HR"
                />
              </label>
              <label>
                Work Order Type
                <select value={createForm.woType} onChange={handleCreateChange("woType")}>
                  {TYPE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Status
                <select value={createForm.status} onChange={handleCreateChange("status")}>
                  {STATUS_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Due Date
                <input type="date" value={createForm.dueDate} onChange={handleCreateChange("dueDate")} />
              </label>
              <label>
                Open Date
                <input type="date" value={createForm.openDate} onChange={handleCreateChange("openDate")} />
              </label>
              <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input
                  type="checkbox"
                  checked={createForm.isScheduled}
                  onChange={handleCreateChange("isScheduled")}
                />
                Scheduled work order
              </label>
            </div>
            <div className="page-section__actions">
              <button type="submit" className="btn btn-primary" disabled={createLoading}>
                {createLoading ? "Creating…" : "Create work order"}
              </button>
            </div>
          </form>

          <section className="page-section">
            <div className="page-section__actions">
              <button className="btn btn-secondary" onClick={() => stubAction("Save/Import")}>
                Save/Import
              </button>
              <button className="btn btn-secondary" onClick={() => stubAction("Columns")}>
                Columns
              </button>
              <button className="btn btn-secondary" onClick={fetchWorkOrders}>
                Refresh
              </button>
              <button className="btn btn-secondary" onClick={() => stubAction("Export Results")}>
                Export Results
              </button>
            </div>

            {error && <div className="card card--error">{error}</div>}
            {notice && <div className="card card--info">{notice}</div>}
            {loading && <div className="card">Loading work orders…</div>}

            <div className="table-responsive">
              <table className="table table-compact table-striped">
                <thead>
                  <tr>
                    <th>Work Order</th>
                    <th>Description</th>
                    <th>Type</th>
                    <th>Open Date</th>
                    <th>Close Date</th>
                    <th>Customer</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {!loading && filteredResults.length === 0 ? (
                    <tr>
                      <td colSpan={7}>No work orders to display.</td>
                    </tr>
                  ) : (
                    filteredResults.map((wo) => (
                      <tr
                        key={wo.id}
                        onClick={() => setSelected(wo)}
                        style={{
                          cursor: "pointer",
                          background:
                            selected?.id === wo.id
                              ? "rgba(56, 189, 248, 0.12)"
                              : undefined,
                        }}
                      >
                        <td>{wo.wo_number || "—"}</td>
                        <td>{wo.description || "—"}</td>
                        <td>{wo.wo_type || "—"}</td>
                        <td>{wo.open_date ? new Date(wo.open_date).toLocaleDateString() : "—"}</td>
                        <td>{wo.closed_date ? new Date(wo.closed_date).toLocaleDateString() : "—"}</td>
                        <td>{wo.originating_org || "—"}</td>
                        <td>{wo.status || "—"}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="work-orders-panel">
              <div className="card-header">
                <h2 className="work-orders-panel__title">Selected Work Order</h2>
                <div className="page-section__actions">
                  <button className="btn btn-primary" onClick={openWorkOrder} disabled={!selected?.id}>
                    Open WO
                  </button>
                  <button className="btn btn-secondary" onClick={() => stubAction("New Aircraft WO")}>
                    New Aircraft WO
                  </button>
                  <button className="btn btn-secondary" onClick={() => stubAction("New Dept. WO")}>
                    New Dept. WO
                  </button>
                </div>
              </div>
              {selected ? (
                <div className="work-orders-panel__fields">
                  <div>
                    <div className="table-secondary-text">Work Order</div>
                    <div className="table-primary-text">{selected.wo_number || "—"}</div>
                  </div>
                  <div>
                    <div className="table-secondary-text">Aircraft</div>
                    <div className="table-primary-text">{selected.aircraft_serial_number || "—"}</div>
                  </div>
                  <div>
                    <div className="table-secondary-text">Status</div>
                    <div className="table-primary-text">{selected.status || "—"}</div>
                  </div>
                  <div>
                    <div className="table-secondary-text">Description</div>
                    <div className="table-primary-text">{selected.description || "—"}</div>
                  </div>
                  <div>
                    <div className="table-secondary-text">Open → Close</div>
                    <div className="table-primary-text">
                      {(selected.open_date && new Date(selected.open_date).toLocaleDateString()) || "—"} →{" "}
                      {(selected.closed_date && new Date(selected.closed_date).toLocaleDateString()) || "—"}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="table-secondary-text">Select a work order to see details.</div>
              )}
            </div>
          </section>
        </div>
      </div>
    </DepartmentLayout>
  );
};

export default WorkOrderSearchPage;
