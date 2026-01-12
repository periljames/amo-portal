import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getCachedUser, getContext } from "../services/auth";
import { DASHBOARD_WIDGETS, getWidgetStorageKey } from "../utils/dashboardWidgets";

type UrlParams = {
  amoCode?: string;
  department?: string;
};

const UserWidgetsPage: React.FC = () => {
  const params = useParams<UrlParams>();
  const navigate = useNavigate();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "planning";

  const currentUser = getCachedUser();
  const userId = currentUser?.id || "unknown";

  const storageKey = getWidgetStorageKey(amoCode, userId, department);
  const [selected, setSelected] = useState<string[]>(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      return raw ? (JSON.parse(raw) as string[]) : [];
    } catch {
      return [];
    }
  });

  const available = useMemo(
    () =>
      DASHBOARD_WIDGETS.filter((widget) =>
        widget.departments.includes(department as any)
      ),
    [department]
  );

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = prev.includes(id) ? prev.filter((v) => v !== id) : [...prev, id];
      localStorage.setItem(storageKey, JSON.stringify(next));
      return next;
    });
  };

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment={department}>
      <header className="page-header">
        <h1 className="page-header__title">Dashboard widgets</h1>
        <p className="page-header__subtitle">
          Choose extra widgets for your {department} dashboard.
        </p>
      </header>

      <section className="page-section">
        <div className="card card--form">
          <h3 style={{ marginTop: 0 }}>Available widgets</h3>
          {available.length === 0 && (
            <p className="text-muted">No widgets available for this department yet.</p>
          )}
          {available.map((widget) => (
            <label
              key={widget.id}
              className="form-row"
              style={{ alignItems: "center", gap: 10 }}
            >
              <input
                type="checkbox"
                checked={selected.includes(widget.id)}
                onChange={() => toggle(widget.id)}
              />
              <span>
                <strong>{widget.label}</strong>
                <div className="text-muted">{widget.description}</div>
              </span>
            </label>
          ))}
        </div>
      </section>

      <section className="page-section">
        <div className="page-section__actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => navigate(`/maintenance/${amoCode}/${department}`)}
          >
            Back to dashboard
          </button>
        </div>
      </section>
    </DepartmentLayout>
  );
};

export default UserWidgetsPage;
