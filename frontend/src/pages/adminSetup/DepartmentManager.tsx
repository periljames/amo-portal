import React, { useMemo, useState } from "react";
import {
  Building2,
  ChevronLeft,
  ChevronRight,
  Pencil,
  Plus,
  Save,
  Search,
  Trash2,
  Users,
  X,
} from "lucide-react";

import { Button, InlineAlert } from "../../components/UI/Admin";
import {
  createSetupDepartment,
  deleteSetupDepartment,
  updateSetupDepartment,
  type SetupDepartmentRead,
} from "../../services/setupDepartments";
import "../../styles/admin-setup-departments.css";

type DepartmentDraft = {
  code: string;
  name: string;
  default_route: string;
  sort_order: string;
  is_active: boolean;
};

type Props = {
  departments: SetupDepartmentRead[];
  loading: boolean;
  onChanged: () => Promise<void> | void;
};

const EMPTY_DEPARTMENT: DepartmentDraft = {
  code: "",
  name: "",
  default_route: "",
  sort_order: "100",
  is_active: true,
};

const PAGE_SIZE_OPTIONS = [6, 10, 20] as const;

function errorText(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  if (error && typeof error === "object") {
    const detail = (error as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return fallback;
}

const DepartmentManager: React.FC<Props> = ({ departments, loading, onChanged }) => {
  const [editor, setEditor] = useState<{ id?: string; draft: DepartmentDraft } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "danger" | "success"; text: string } | null>(null);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(PAGE_SIZE_OPTIONS[0]);

  const filteredDepartments = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return departments;
    return departments.filter((department) => [
      department.code,
      department.name,
      department.default_route || "",
      department.is_active ? "active" : "inactive",
    ].some((value) => value.toLocaleLowerCase().includes(normalized)));
  }, [departments, query]);

  const pageCount = Math.max(1, Math.ceil(filteredDepartments.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const pageStartIndex = (currentPage - 1) * pageSize;
  const visibleDepartments = filteredDepartments.slice(pageStartIndex, pageStartIndex + pageSize);
  const visibleStart = filteredDepartments.length ? pageStartIndex + 1 : 0;
  const visibleEnd = Math.min(pageStartIndex + pageSize, filteredDepartments.length);

  const startEditor = (department?: SetupDepartmentRead) => {
    setMessage(null);
    setEditor({
      id: department?.id,
      draft: department ? {
        code: department.code,
        name: department.name,
        default_route: department.default_route || "",
        sort_order: String(department.sort_order ?? 100),
        is_active: department.is_active,
      } : { ...EMPTY_DEPARTMENT },
    });
  };

  const saveDepartment = async () => {
    if (!editor) return;
    const code = editor.draft.code.trim().toUpperCase().replaceAll("-", "_").replace(/\s+/g, "_");
    const name = editor.draft.name.trim();
    if (!code || !name) {
      setMessage({ tone: "danger", text: "Department code and name are required." });
      return;
    }

    const editingExisting = Boolean(editor.id);
    setBusyId(editor.id || "new");
    setMessage(null);
    try {
      const payload = {
        code,
        name,
        default_route: editor.draft.default_route.trim() || null,
        sort_order: Number(editor.draft.sort_order || 100),
        is_active: editor.draft.is_active,
      };
      if (editor.id) await updateSetupDepartment(editor.id, payload);
      else await createSetupDepartment(payload);
      setMessage({ tone: "success", text: editingExisting ? "Department updated." : "Department created." });
      setEditor(null);
      if (!editingExisting) {
        setQuery("");
        setPage(1);
      }
      await onChanged();
    } catch (error) {
      setMessage({ tone: "danger", text: errorText(error, "Could not save the department.") });
    } finally {
      setBusyId(null);
    }
  };

  const toggleDepartment = async (department: SetupDepartmentRead) => {
    const nextActive = !department.is_active;
    if (!window.confirm(`${nextActive ? "Reactivate" : "Deactivate"} ${department.code} · ${department.name}?`)) return;
    setBusyId(department.id);
    setMessage(null);
    try {
      await updateSetupDepartment(department.id, { is_active: nextActive });
      setMessage({ tone: "success", text: `${department.code} ${nextActive ? "reactivated" : "deactivated"}.` });
      await onChanged();
    } catch (error) {
      setMessage({ tone: "danger", text: errorText(error, "Could not update the department.") });
    } finally {
      setBusyId(null);
    }
  };

  const removeDepartment = async (department: SetupDepartmentRead) => {
    if (department.assigned_user_count > 0) {
      setMessage({ tone: "danger", text: `Reassign the ${department.assigned_user_count} user(s) in ${department.code} before deleting it. You may deactivate it immediately.` });
      return;
    }
    if (!window.confirm(`Permanently delete ${department.code} · ${department.name}? This is only permitted when no operational record references it.`)) return;
    setBusyId(department.id);
    setMessage(null);
    try {
      await deleteSetupDepartment(department.id);
      setMessage({ tone: "success", text: `${department.code} deleted.` });
      await onChanged();
    } catch (error) {
      setMessage({ tone: "danger", text: errorText(error, "Could not delete the department.") });
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <section className="setup-department-manager" aria-labelledby="departmentManagerTitle">
        <div className="setup-centre__section-heading">
          <div>
            <span>Tenant-owned organisation</span>
            <h2 id="departmentManagerTitle">Departments and accountable ownership</h2>
            <p>Departments are real AMO records. Create, rename, route, order, deactivate or safely delete them here.</p>
          </div>
          <button type="button" className="setup-centre__primary-action" onClick={() => startEditor()}>
            <Plus size={16} /> Add department
          </button>
        </div>

        {message ? (
          <InlineAlert tone={message.tone} title={message.tone === "danger" ? "Department action needs attention" : "Department saved"}>
            <span>{message.text}</span>
          </InlineAlert>
        ) : null}

        {loading ? (
          <div className="setup-centre__loading">Loading departments…</div>
        ) : departments.length ? (
          <>
            <div className="setup-department-manager__toolbar">
              <label className="setup-department-manager__search">
                <Search size={15} aria-hidden="true" />
                <input
                  type="search"
                  value={query}
                  aria-label="Search departments"
                  placeholder="Search code, name, route or status"
                  onChange={(event) => {
                    setQuery(event.target.value);
                    setPage(1);
                  }}
                />
                {query ? (
                  <button type="button" aria-label="Clear department search" onClick={() => { setQuery(""); setPage(1); }}>
                    <X size={14} />
                  </button>
                ) : null}
              </label>
              <span className="setup-department-manager__count">
                {filteredDepartments.length === departments.length
                  ? `${departments.length} department${departments.length === 1 ? "" : "s"}`
                  : `${filteredDepartments.length} of ${departments.length} departments`}
              </span>
            </div>

            {filteredDepartments.length ? (
              <>
                <div
                  className="setup-department-table"
                  role="table"
                  aria-label="AMO departments"
                  aria-rowcount={filteredDepartments.length}
                >
                  <div className="setup-department-table__head" role="row">
                    <span role="columnheader">Department</span>
                    <span role="columnheader">Default route</span>
                    <span role="columnheader">Users</span>
                    <span role="columnheader">Status</span>
                    <span role="columnheader">Actions</span>
                  </div>
                  <div className="setup-department-table__body" role="rowgroup">
                    {visibleDepartments.map((department) => (
                      <article
                        key={department.id}
                        role="row"
                        className={`setup-department-table__row${department.is_active ? "" : " is-inactive"}`}
                      >
                        <div className="setup-department-table__identity" role="cell">
                          <Building2 size={17} />
                          <div>
                            <strong title={department.code}>{department.code}</strong>
                            <span title={department.name}>{department.name}</span>
                          </div>
                        </div>
                        <code className="setup-department-table__route" role="cell" title={department.default_route || "No default route"}>
                          {department.default_route || "No default route"}
                        </code>
                        <span className="setup-department-table__users" role="cell">
                          <Users size={14} /> {department.assigned_user_count}
                        </span>
                        <span
                          className={`setup-department-table__status${department.is_active ? "" : " is-inactive"}`}
                          role="cell"
                        >
                          {department.is_active ? "Active" : "Inactive"}
                        </span>
                        <div className="setup-department-table__actions" role="cell">
                          <button type="button" disabled={busyId === department.id} onClick={() => startEditor(department)}>
                            <Pencil size={13} /> Edit
                          </button>
                          <button type="button" disabled={busyId === department.id} onClick={() => void toggleDepartment(department)}>
                            {department.is_active ? "Deactivate" : "Reactivate"}
                          </button>
                          <button
                            type="button"
                            disabled={busyId === department.id || department.assigned_user_count > 0}
                            title={department.assigned_user_count > 0 ? "Reassign users before deletion" : "Delete department"}
                            onClick={() => void removeDepartment(department)}
                          >
                            <Trash2 size={13} /> Delete
                          </button>
                        </div>
                      </article>
                    ))}
                  </div>
                </div>

                <div className="setup-department-manager__footer" aria-label="Department pagination">
                  <span className="setup-department-manager__range" aria-live="polite">
                    Showing {visibleStart}–{visibleEnd} of {filteredDepartments.length}
                  </span>
                  <label className="setup-department-manager__page-size">
                    Rows
                    <select
                      value={pageSize}
                      aria-label="Departments per page"
                      onChange={(event) => {
                        setPageSize(Number(event.target.value));
                        setPage(1);
                      }}
                    >
                      {PAGE_SIZE_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}
                    </select>
                  </label>
                  <div className="setup-department-manager__pager">
                    <button type="button" aria-label="Previous department page" disabled={currentPage <= 1} onClick={() => setPage(Math.max(1, currentPage - 1))}>
                      <ChevronLeft size={15} />
                    </button>
                    <span>Page {currentPage} of {pageCount}</span>
                    <button type="button" aria-label="Next department page" disabled={currentPage >= pageCount} onClick={() => setPage(Math.min(pageCount, currentPage + 1))}>
                      <ChevronRight size={15} />
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <div className="setup-department-manager__filter-empty">
                <Search size={24} />
                <strong>No matching department</strong>
                <span>Try a different code, name, route or status.</span>
                <button type="button" onClick={() => { setQuery(""); setPage(1); }}>Clear search</button>
              </div>
            )}
          </>
        ) : (
          <div className="setup-centre__empty">
            <Building2 size={28} />
            <strong>No departments exist</strong>
            <p>Create the AMO&apos;s real departments here. The portal will not silently repopulate a hard-coded list.</p>
            <button type="button" onClick={() => startEditor()}><Plus size={16} /> Create first department</button>
          </div>
        )}
      </section>

      {editor ? (
        <div className="setup-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setEditor(null); }}>
          <section className="setup-dialog" role="dialog" aria-modal="true" aria-labelledby="departmentEditorTitle">
            <div className="setup-dialog__header">
              <div><span>Organisation record</span><h2 id="departmentEditorTitle">{editor.id ? "Edit department" : "Add department"}</h2></div>
              <button type="button" aria-label="Close department editor" onClick={() => setEditor(null)}><X size={18} /></button>
            </div>
            <div className="setup-dialog__grid">
              <label><span>Code *</span><input value={editor.draft.code} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, code: event.target.value } })} placeholder="QUALITY" /></label>
              <label><span>Name *</span><input value={editor.draft.name} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, name: event.target.value } })} placeholder="Quality Assurance" /></label>
              <label className="is-wide"><span>Default portal route</span><input value={editor.draft.default_route} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, default_route: event.target.value } })} placeholder="/quality/dashboard" /></label>
              <label><span>Display order</span><input type="number" min={0} max={100000} value={editor.draft.sort_order} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, sort_order: event.target.value } })} /></label>
              <label className="setup-dialog__check"><input type="checkbox" checked={editor.draft.is_active} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, is_active: event.target.checked } })} /><span>Active and available for user assignment</span></label>
            </div>
            <div className="setup-dialog__actions">
              <Button type="button" variant="secondary" onClick={() => setEditor(null)}>Cancel</Button>
              <Button type="button" disabled={busyId !== null} onClick={() => void saveDepartment()}>
                <Save size={16} /> {busyId ? "Saving…" : editor.id ? "Save changes" : "Create department"}
              </Button>
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
};

export default DepartmentManager;
