import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { listWorkbookCatalog } from "./reliabilityWorkbookParityApi";
import { ReliabilityManagementReports } from "./ReliabilityManagementReports";
import { ReliabilityMappingParity, ReliabilityStatisticalAlerts } from "./ReliabilityWorkbookGovernance";
import { ReliabilityStructuredCsvImport } from "./ReliabilityStructuredCsvImport";
import { ReliabilityWorkbookImports } from "./ReliabilityWorkbookImports";
import { ReliabilityWorkbookRegisters } from "./ReliabilityWorkbookRegisters";
import { ReliabilityWorkbookReports } from "./ReliabilityWorkbookReports";
import { ReliabilityWorkbenchProvider, WorkbenchPreferenceBar } from "./ReliabilityWorkbenchControls";
import type { WorkbookDatasetCode, WorkbookFieldDefinition, WorkspaceSection } from "./reliabilityWorkbookParityTypes";
import "../../styles/reliability-v2.css";
import "./ReliabilityWorkbookParityWorkspace.css";
import "./ReliabilityWorkbenchControls.css";

const SECTIONS: Array<{ id: WorkspaceSection; label: string; description: string; route: string }> = [
  { id: "registers", label: "Source registers", description: "Sixteen controlled Reliability datasets with lifecycle and provenance", route: "workbook-registers" },
  { id: "alerts", label: "Statistical alerts", description: "Exact limits, exposure quality and retained analytical evidence", route: "statistical-alerts" },
  { id: "mapping", label: "Mapping & imports", description: "Canonical CSV, workbook intake, field parity and validation", route: "workbook-mapping" },
  { id: "reports", label: "Report layouts", description: "Daily-to-quarter management packs, layouts, links and retained outputs", route: "workbook-reports" },
];

function sectionFromPath(pathname: string): WorkspaceSection {
  const route = pathname.split("/reliability/")[1]?.split("/")[0] || "workbook-registers";
  return SECTIONS.find((item) => item.route === route)?.id || "registers";
}

const ReliabilityWorkbookParityWorkspace: React.FC = () => {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const basePath = `/maintenance/${encodeURIComponent(amoCode)}/reliability`;
  const [section, setSection] = useState<WorkspaceSection>(() => sectionFromPath(location.pathname));
  const [catalog, setCatalog] = useState<WorkbookFieldDefinition[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<WorkbookDatasetCode>("AU");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setSection(sectionFromPath(location.pathname)), [location.pathname]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await listWorkbookCatalog();
        if (!active) return;
        setCatalog(result);
        setSelectedDataset((current) => result.some((item) => item.code === current) ? current : result[0]?.code || "AU");
      } catch (caught: unknown) {
        if (active) setError(caught instanceof Error ? caught.message : "The workbook parity catalogue could not be loaded.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, []);

  const selectSection = (item: (typeof SECTIONS)[number]) => {
    setSection(item.id);
    navigate(`${basePath}/${item.route}`);
  };

  return <ReliabilityWorkbenchProvider>
    <DepartmentLayout amoCode={amoCode} activeDepartment="reliability">
      <main className="rel-wp" data-testid="reliability-workbook-parity">
        <header className="rel-wp__header">
          <div>
            <p className="rel-wp__eyebrow">Controlled Reliability programme data</p>
            <h1>Reliability programme workbench</h1>
            <p>Enter once, validate once and reuse the approved evidence for daily analysis, management reporting, controlled exports and later regulatory programme reviews.</p>
          </div>
          <div className="rel-wp__header-actions">
            <Link className="btn btn-secondary" to={basePath}>Analytics dashboard</Link>
            <Link className="btn btn-secondary" to={`${basePath}/operations`}>Operational sources</Link>
            <Link className="btn btn-secondary" to={`${basePath}/events`}>Canonical events</Link>
          </div>
        </header>

        <WorkbenchPreferenceBar />
        <p className="rel-wp__guided-tip">Use compact view for spreadsheet-style review. Ctrl/Cmd-click rows to select several, right-click any table row for safe copy/export and column actions, and use arrow keys to move between cells.</p>

        <nav className="rel-wp__tabs" aria-label="Workbook parity workspaces">
          {SECTIONS.map((item) => <button key={item.id} type="button" className={section === item.id ? "is-active" : ""} aria-current={section === item.id ? "page" : undefined} onClick={() => selectSection(item)}>
            <strong>{item.label}</strong><span>{item.description}</span>
          </button>)}
        </nav>

        {loading && <div className="rel-wp__loading" role="status">Loading controlled workbook definitions…</div>}
        {error && <div className="rel-wp__error" role="alert">{error}</div>}
        {!loading && !error && <>
          {section === "registers" && <ReliabilityWorkbookRegisters catalog={catalog} selectedDataset={selectedDataset} onDatasetChange={setSelectedDataset} />}
          {section === "alerts" && <ReliabilityStatisticalAlerts catalog={catalog} />}
          {section === "mapping" && <div className="rel-wp__stack"><ReliabilityStructuredCsvImport catalog={catalog} /><ReliabilityMappingParity catalog={catalog} /><ReliabilityWorkbookImports catalog={catalog} /></div>}
          {section === "reports" && <div className="rel-wp__stack"><ReliabilityManagementReports /><ReliabilityWorkbookReports /></div>}
        </>}
      </main>
    </DepartmentLayout>
  </ReliabilityWorkbenchProvider>;
};

export default ReliabilityWorkbookParityWorkspace;