import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { listWorkbookCatalog } from "./reliabilityWorkbookParityApi";
import { ReliabilityMappingParity, ReliabilityStatisticalAlerts } from "./ReliabilityWorkbookGovernance";
import { ReliabilityWorkbookRegisters } from "./ReliabilityWorkbookRegisters";
import { ReliabilityWorkbookReports } from "./ReliabilityWorkbookReports";
import type { WorkbookDatasetCode, WorkbookFieldDefinition, WorkspaceSection } from "./reliabilityWorkbookParityTypes";
import "../../styles/reliability-v2.css";
import "./ReliabilityWorkbookParityWorkspace.css";

const SECTIONS: Array<{ id: WorkspaceSection; label: string; description: string }> = [
  { id: "registers", label: "Source registers", description: "AU, AI, PM, OOS, removals, scheduled findings, structures, recurrence and ECTM" },
  { id: "alerts", label: "Statistical alerts", description: "Mean, sample standard deviation, warning and alert limits" },
  { id: "mapping", label: "Mapping & parity", description: "C208B, DHC8 and operator workbook field contracts" },
  { id: "reports", label: "Report layouts", description: "Versioned programme layouts, preview and retained outputs" },
];

const ReliabilityWorkbookParityWorkspace: React.FC = () => {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const basePath = `/maintenance/${encodeURIComponent(amoCode)}/reliability`;
  const [section, setSection] = useState<WorkspaceSection>("registers");
  const [catalog, setCatalog] = useState<WorkbookFieldDefinition[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<WorkbookDatasetCode>("AU");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await listWorkbookCatalog();
        if (!active) return;
        setCatalog(result);
        if (result.length && !result.some((item) => item.code === selectedDataset)) setSelectedDataset(result[0].code);
      } catch (caught: unknown) {
        if (active) setError(caught instanceof Error ? caught.message : "The workbook parity catalogue could not be loaded.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [selectedDataset]);

  return <DepartmentLayout amoCode={amoCode} activeDepartment="reliability">
    <main className="rel-wp" data-testid="reliability-workbook-parity">
      <header className="rel-wp__header">
        <div>
          <p className="rel-wp__eyebrow">Controlled Reliability programme data</p>
          <h1>Workbook parity control centre</h1>
          <p>Replace the C208B, DHC8 and operator analysis workbooks with governed source records, statistical calculations and retained reports.</p>
        </div>
        <div className="rel-wp__header-actions">
          <Link className="btn btn-secondary" to={basePath}>Analytics dashboard</Link>
          <Link className="btn btn-secondary" to={`${basePath}/operations`}>Operational sources</Link>
          <Link className="btn btn-secondary" to={`${basePath}/events`}>Canonical events</Link>
        </div>
      </header>

      <nav className="rel-wp__tabs" aria-label="Workbook parity workspaces">
        {SECTIONS.map((item) => <button key={item.id} type="button" className={section === item.id ? "is-active" : ""} onClick={() => setSection(item.id)}>
          <strong>{item.label}</strong><span>{item.description}</span>
        </button>)}
      </nav>

      {loading && <div className="rel-wp__loading" role="status">Loading controlled workbook definitions…</div>}
      {error && <div className="rel-wp__error" role="alert">{error}</div>}
      {!loading && !error && <>
        {section === "registers" && <ReliabilityWorkbookRegisters catalog={catalog} selectedDataset={selectedDataset} onDatasetChange={setSelectedDataset} />}
        {section === "alerts" && <ReliabilityStatisticalAlerts catalog={catalog} />}
        {section === "mapping" && <ReliabilityMappingParity catalog={catalog} />}
        {section === "reports" && <ReliabilityWorkbookReports />}
      </>}
    </main>
  </DepartmentLayout>;
};

export default ReliabilityWorkbookParityWorkspace;
