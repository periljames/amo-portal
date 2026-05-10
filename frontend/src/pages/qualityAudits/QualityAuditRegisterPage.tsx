import React, { useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ClipboardList, ShieldAlert, TableProperties } from "lucide-react";
import SpreadsheetToolbar from "../../components/shared/SpreadsheetToolbar";
import { ResponsiveSegmentedControl } from "../../components/QMS/ResponsiveSegmentedControl";
import { useDensityPreference } from "../../hooks/useDensityPreference";
import { getContext } from "../../services/auth";
import { qmsGetAuditRegister, type CAROut, type QMSAuditOut, type QMSFindingOut } from "../../services/qms";
import { buildAuditWorkspacePath } from "../../utils/auditSlug";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";

type RegisterTab = "findings" | "cars";

type RegisterRow = {
  audit: QMSAuditOut;
  finding: QMSFindingOut;
  linkedCars: CAROut[];
};

const QualityAuditRegisterPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get("tab");
  const tab: RegisterTab = rawTab === "cars" ? "cars" : "findings";
  const auditId = searchParams.get("auditId")?.trim() || "";
  const [wrapText, setWrapText] = useState(false);
  const [showFilters, setShowFilters] = useState(true);
  const [showOwner, setShowOwner] = useState(true);
  const [quickFilter, setQuickFilter] = useState("");
  const [headerFilters, setHeaderFilters] = useState({
    ref: "",
    finding: "",
    audit: "",
    type: "",
    owner: "",
    car: "",
  });
  const { density, setDensity } = useDensityPreference("audit-register", "compact");

  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const navigate = useNavigate();

  const registerQuery = useQuery({
    queryKey: ["qms-audit-register", amoCode],
    queryFn: () => qmsGetAuditRegister({ domain: "AMO" }),
    staleTime: 60_000,
  });

  const rows = useMemo<RegisterRow[]>(() => {
    return (registerQuery.data?.rows ?? []).map((row) => ({
      audit: row.audit,
      finding: row.finding,
      linkedCars: row.linked_cars,
    }));
  }, [registerQuery.data]);

  const filteredRows = useMemo(() => {
    const q = quickFilter.trim().toLowerCase();
    return rows.filter(({ audit, finding, linkedCars }) => {
      if (auditId && audit.id !== auditId) return false;
      if (tab === "cars" && linkedCars.length === 0) return false;
      const haystack = [
        audit.audit_ref,
        audit.title,
        finding.finding_ref || finding.id,
        finding.description,
        finding.finding_type,
        finding.acknowledged_by_name || "",
        ...linkedCars.map((car) => `${car.car_number} ${car.title} ${car.summary}`),
      ]
        .join(" ")
        .toLowerCase();

      if (q && !haystack.includes(q)) return false;
      if (headerFilters.ref && !(finding.finding_ref || finding.id).toLowerCase().includes(headerFilters.ref.toLowerCase())) return false;
      if (headerFilters.finding && !finding.description.toLowerCase().includes(headerFilters.finding.toLowerCase())) return false;
      if (headerFilters.audit && !`${audit.audit_ref} ${audit.title}`.toLowerCase().includes(headerFilters.audit.toLowerCase())) return false;
      if (headerFilters.type && !finding.finding_type.toLowerCase().includes(headerFilters.type.toLowerCase())) return false;
      if (headerFilters.owner && !(finding.acknowledged_by_name || "").toLowerCase().includes(headerFilters.owner.toLowerCase())) return false;
      if (headerFilters.car && !linkedCars.some((car) => `${car.car_number} ${car.title}`.toLowerCase().includes(headerFilters.car.toLowerCase()))) return false;
      return true;
    });
  }, [headerFilters, quickFilter, rows, tab]);

  const loading = registerQuery.isLoading;
  const cellTextClass = wrapText ? "qms-cell-text qms-cell-text--wrap" : "qms-cell-text qms-cell-text--truncate";

  return (
    <QualityAuditsSectionLayout
      title="Register"
      subtitle="Operational closeout register for findings and linked CAR actions."
      toolbar={
        <ResponsiveSegmentedControl
          label="Register dataset"
          value={tab}
          onChange={(nextTab: RegisterTab) => {
            const next = new URLSearchParams(searchParams);
            next.set("tab", nextTab);
            if (auditId) next.set("auditId", auditId);
            setSearchParams(next);
          }}
          compactIconsOnMobile
          options={[
            { value: "findings", label: "Findings", icon: ClipboardList },
            { value: "cars", label: "CARs", icon: ShieldAlert },
          ]}
        />
      }
    >
      <div className="audit-workspace">
        <div className="audit-workspace__toolbar-row">
          <label className="audit-search" aria-label="Quick filter register rows">
            <TableProperties size={15} />
            <input
              value={quickFilter}
              onChange={(event) => setQuickFilter(event.target.value)}
              placeholder="Quick filter across audit ref, finding, owner, CAR, and summary"
            />
          </label>
          <SpreadsheetToolbar
            density={density}
            onDensityChange={setDensity}
            wrapText={wrapText}
            onWrapTextChange={setWrapText}
            showFilters={showFilters}
            onShowFiltersChange={setShowFilters}
            columnToggles={[
              { id: "owner", label: "Owner", checked: showOwner, onToggle: () => setShowOwner((current) => !current) },
            ]}
          />
        </div>

        <div className="audit-panel">
          <div className="audit-panel__header">
            <div>
              <h2 className="audit-panel__title">Closeout register</h2>
              <p className="audit-panel__subtitle">{filteredRows.length} visible rows · {tab === "cars" ? "CAR-linked findings only" : "all findings"}</p>
            </div>
            <span className="qms-pill">{density === "compact" ? "Compact density" : "Comfortable density"}</span>
          </div>
          <div className="table-wrapper">
            <table className={`table ${density === "compact" ? "table-row--compact" : "table-row--comfortable"} ${wrapText ? "table--wrap" : ""}`}>
              <thead>
                <tr>
                  <th>Finding ref</th>
                  <th>Audit ref</th>
                  <th>Finding</th>
                  <th>Type</th>
                  {showOwner ? <th>Owner</th> : null}
                  <th>Linked CARs</th>
                  <th>Action</th>
                </tr>
                {showFilters ? (
                  <tr>
                    <th><input className="input" placeholder="Find ref" value={headerFilters.ref} onChange={(event) => setHeaderFilters((current) => ({ ...current, ref: event.target.value }))} /></th>
                    <th><input className="input" placeholder="Audit ref / title" value={headerFilters.audit} onChange={(event) => setHeaderFilters((current) => ({ ...current, audit: event.target.value }))} /></th>
                    <th><input className="input" placeholder="Finding text" value={headerFilters.finding} onChange={(event) => setHeaderFilters((current) => ({ ...current, finding: event.target.value }))} /></th>
                    <th><input className="input" placeholder="Type" value={headerFilters.type} onChange={(event) => setHeaderFilters((current) => ({ ...current, type: event.target.value }))} /></th>
                    {showOwner ? <th><input className="input" placeholder="Owner" value={headerFilters.owner} onChange={(event) => setHeaderFilters((current) => ({ ...current, owner: event.target.value }))} /></th> : null}
                    <th><input className="input" placeholder="CAR number / title" value={headerFilters.car} onChange={(event) => setHeaderFilters((current) => ({ ...current, car: event.target.value }))} /></th>
                    <th />
                  </tr>
                ) : null}
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={showOwner ? 7 : 6}>Loading register…</td>
                  </tr>
                ) : filteredRows.length === 0 ? (
                  <tr>
                    <td colSpan={showOwner ? 7 : 6}>No register rows match the current filters.</td>
                  </tr>
                ) : (
                  filteredRows.map(({ audit, finding, linkedCars }) => (
                    <tr key={finding.id}>
                      <td>{finding.finding_ref || finding.id}</td>
                      <td>
                        <strong>{audit.audit_ref}</strong>
                        <div className={`text-muted ${cellTextClass}`}>{audit.title}</div>
                      </td>
                      <td>
                        <div className={cellTextClass}>{finding.description}</div>
                        <div className={`text-muted ${cellTextClass}`}>{finding.objective_evidence || "No objective evidence captured."}</div>
                      </td>
                      <td><span className="qms-pill">{finding.finding_type}</span></td>
                      {showOwner ? <td>{finding.acknowledged_by_name || "Unassigned"}</td> : null}
                      <td>
                        <div className="audit-chip-list">
                          {linkedCars.length === 0 ? <span className="text-muted">No linked CARs</span> : linkedCars.map((car) => (
                            <button
                              key={car.id}
                              type="button"
                              onClick={() => navigate(`/maintenance/${amoCode}/qms/cars?carId=${car.id}`)}
                              className="secondary-chip-btn"
                              title={`${car.car_number} · ${car.title}`}
                            >
                              {car.car_number}
                            </button>
                          ))}
                        </div>
                      </td>
                      <td>
                        <button
                          type="button"
                          onClick={() => navigate(buildAuditWorkspacePath({ amoCode, department, auditRef: audit.audit_ref }))}
                          className="secondary-chip-btn"
                        >
                          View audit
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="audit-stats-grid">
          <div className="audit-stat-card">
            <div className="audit-stat-card__label"><ClipboardList size={15} /> Findings in scope</div>
            <div className="audit-stat-card__value">{rows.length}</div>
          </div>
          <div className="audit-stat-card">
            <div className="audit-stat-card__label"><ShieldAlert size={15} /> Findings with CARs</div>
            <div className="audit-stat-card__value">{rows.filter((row) => row.linkedCars.length > 0).length}</div>
          </div>
          <div className="audit-stat-card">
            <div className="audit-stat-card__label"><AlertTriangle size={15} /> Open CAR count</div>
            <div className="audit-stat-card__value">{rows.flatMap((row) => row.linkedCars).filter((car) => car.status !== "CLOSED").length}</div>
          </div>
        </div>
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditRegisterPage;
