// src/pages/work/TaskSummaryPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getContext } from "../../services/auth";
import {
  getTask,
  getWorkOrder,
  updateTask,
  type TaskCardRead,
  type TaskUpdatePayload,
  type WorkOrderRead,
} from "../../services/workOrders";

type UrlParams = {
  amoCode?: string;
  department?: string;
  taskId?: string;
};

type SectionKey =
  | "details"
  | "defect"
  | "planning"
  | "skills"
  | "flight"
  | "technical"
  | "tools";

const SECTION_LABELS: Record<SectionKey, string> = {
  details: "Details",
  defect: "Defect",
  planning: "Planning",
  skills: "Skills",
  flight: "Flight Log",
  technical: "Technical Logs",
  tools: "Tools",
};

const tabs = ["Summary", "Worksteps", "Required Parts", "Services"] as const;
type TabKey = (typeof tabs)[number];

const TaskSummaryPage: React.FC = () => {
  const { amoCode, department, taskId } = useParams<UrlParams>();
  const context = getContext();
  const resolvedAmoCode = amoCode || context.amoSlug || "system";
  const activeDepartment = (department || context.department || "planning").toLowerCase();
  const basePath = `/maintenance/${resolvedAmoCode}/${activeDepartment}`;
  const id = Number(taskId);
  const [task, setTask] = useState<TaskCardRead | null>(null);
  const [workOrder, setWorkOrder] = useState<WorkOrderRead | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("Summary");
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Record<SectionKey, boolean>>({
    details: false,
    defect: true,
    planning: false,
    skills: true,
    flight: true,
    technical: true,
    tools: true,
  });

  useEffect(() => {
    if (!id || Number.isNaN(id)) return;
    const load = async () => {
      setLoading(true);
      setError(null);
      setNotice(null);
      try {
        const taskData = await getTask(id);
        setTask(taskData);
        if (taskData.work_order_id) {
          const wo = await getWorkOrder(taskData.work_order_id);
          setWorkOrder(wo);
        }
      } catch (e: any) {
        console.error("Failed to load task", e);
        setError(e?.message || "Could not load task.");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [id]);

  const toggleAll = () => {
    const allCollapsed = Object.values(collapsed).every(Boolean);
    const next = Object.keys(collapsed).reduce((acc, key) => {
      acc[key as SectionKey] = !allCollapsed;
      return acc;
    }, {} as Record<SectionKey, boolean>);
    setCollapsed(next);
  };

  const handlePrint = () => {
    if (!task?.id) return;
    window.open(`${basePath}/tasks/${task.id}/print`, "_blank", "noopener");
  };

  const handleEdit = async () => {
    if (!task?.id || !task.updated_at) {
      setNotice("Task data not ready for edits yet.");
      return;
    }
    setNotice(null);
    try {
      const payload: TaskUpdatePayload = {
        last_known_updated_at: task.updated_at,
        hf_notes: task.hf_notes || "",
      };
      const updated = await updateTask(task.id, payload);
      setTask(updated);
      setNotice("Task updated.");
    } catch (e: any) {
      console.error("Failed to update task", e);
      setError(e?.message || "Could not update task.");
    }
  };

  const summaryFields = useMemo(
    () => [
      { label: "Work Order", value: workOrder?.wo_number || "—" },
      { label: "Task", value: task?.task_code || task?.id || "—" },
      { label: "Aircraft", value: task?.aircraft_serial_number || "—" },
      { label: "Status", value: task?.status || "—" },
      { label: "Origin", value: task?.origin_type || "—" },
      {
        label: "Created",
        value: task?.created_at ? new Date(task.created_at).toLocaleString() : "—",
      },
    ],
    [task, workOrder]
  );

  const renderSectionBody = (key: SectionKey) => {
    if (!task) return "No task data yet.";
    switch (key) {
      case "details":
        return (
          <div className="page-section__grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
            <div>
              <div className="table-secondary-text">Title</div>
              <div className="table-primary-text">{task.title || "—"}</div>
            </div>
            <div>
              <div className="table-secondary-text">ATA</div>
              <div className="table-primary-text">{task.ata_chapter || "—"}</div>
            </div>
            <div>
              <div className="table-secondary-text">Zone</div>
              <div className="table-primary-text">{task.zone || "—"}</div>
            </div>
            <div>
              <div className="table-secondary-text">Access Panel</div>
              <div className="table-primary-text">{task.access_panel || "—"}</div>
            </div>
            <div>
              <div className="table-secondary-text">Description</div>
              <div className="table-primary-text">{task.description || "—"}</div>
            </div>
          </div>
        );
      case "planning":
        return (
          <div className="page-section__grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
            <div>
              <div className="table-secondary-text">Planned Start</div>
              <div className="table-primary-text">
                {task.planned_start ? new Date(task.planned_start).toLocaleString() : "—"}
              </div>
            </div>
            <div>
              <div className="table-secondary-text">Planned End</div>
              <div className="table-primary-text">
                {task.planned_end ? new Date(task.planned_end).toLocaleString() : "—"}
              </div>
            </div>
            <div>
              <div className="table-secondary-text">Estimated Hours</div>
              <div className="table-primary-text">{task.estimated_manhours ?? "—"}</div>
            </div>
            <div>
              <div className="table-secondary-text">Priority</div>
              <div className="table-primary-text">{task.priority || "—"}</div>
            </div>
          </div>
        );
      default:
        return (
          <div className="collapse-summary">
            Not available yet. Backend endpoints or fields are pending for this section.
          </div>
        );
    }
  };

  return (
    <DepartmentLayout amoCode={resolvedAmoCode} activeDepartment={activeDepartment}>
      <div className="page-layout">
        <div className="page-header">
          <h1 className="page-header__title">Task Summary</h1>
          <p className="page-header__subtitle">
            {task?.title || "Task"} • {task?.aircraft_serial_number || "—"}
          </p>
        </div>

        {error && <div className="card card--error">{error}</div>}
        {notice && <div className="card card--info">{notice}</div>}
        {loading && <div className="card">Loading task summary…</div>}

        <section className="page-section">
          <div className="page-section__grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
            {summaryFields.map((field) => (
              <div key={field.label}>
                <div className="table-secondary-text">{field.label}</div>
                <div className="table-primary-text">{field.value}</div>
              </div>
            ))}
          </div>
          <div className="page-section__actions">
            <button className="btn btn-secondary" onClick={toggleAll}>
              Expand/Collapse All
            </button>
            <button className="btn btn-secondary" onClick={handleEdit}>
              Edit
            </button>
            <button className="btn btn-primary" onClick={handlePrint}>
              Print
            </button>
          </div>
        </section>

        <section className="page-section">
          <div className="tab-list">
            {tabs.map((tab) => (
              <button
                key={tab}
                type="button"
                className={`tab-button${activeTab === tab ? " is-active" : ""}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab}
              </button>
            ))}
          </div>

          {activeTab === "Summary" && (
            <div className="page-section__grid" style={{ gap: 12 }}>
              {(Object.keys(SECTION_LABELS) as SectionKey[]).map((key) => (
                <div className="collapse-card" key={key}>
                  <div
                    className="collapse-header"
                    onClick={() => setCollapsed((prev) => ({ ...prev, [key]: !prev[key] }))}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setCollapsed((prev) => ({ ...prev, [key]: !prev[key] }));
                      }
                    }}
                  >
                    <div className="table-primary-text">{SECTION_LABELS[key]}</div>
                    <div className="collapse-summary">{collapsed[key] ? "Expand" : "Collapse"}</div>
                  </div>
                  {!collapsed[key] && <div className="collapse-body">{renderSectionBody(key)}</div>}
                </div>
              ))}
            </div>
          )}

          {activeTab !== "Summary" && (
            <div className="collapse-summary" style={{ padding: 12 }}>
              {activeTab} data is not available yet. Backend endpoints are pending for this tab.
            </div>
          )}
        </section>
      </div>
    </DepartmentLayout>
  );
};

export default TaskSummaryPage;
