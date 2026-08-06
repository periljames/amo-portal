import React, { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { apiRequest } from "../../services/apiClient";
import { listAircraft, type AircraftRead } from "../../services/fleet";
import { ReliabilityWorkbookMappingGovernance, ReliabilityWorkbookReportGovernance } from "./ReliabilityWorkbookGovernance";
import { ReliabilityWorkbookRegisters } from "./ReliabilityWorkbookRegisters";
import { ReliabilityWorkbookStatisticalAlerts } from "./ReliabilityWorkbookStatisticalAlerts";
import type {
  DatasetDefinition,
  OosMetrics,
  ParityRow,
  ReportLayout,
  ReportSnapshot,
  StatisticalAlert,
  WorkbookDatasetCode,
  WorkbookRecord,
  WorkspaceSection,
} from "./reliabilityWorkbookParityTypes";
import "../../styles/reliability-v2.css";
import "./ReliabilityWorkbookParityWorkspace.css";

const PAGE_SIZE = 50;

function startOfRollingYear(): string {
  const date = new Date();
  date.setFullYear(date.getFullYear() - 1);
  return date.toISOString().slice(0, 10);
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

const SECTIONS: Array<{ id: WorkspaceSection; label: string; description: string }> = [
  { id: "registers", label: "Source registers", description: "AU, AI, PM, OOS, RM, SM, Structures, Recurring Defects and ECTM." },
  { id: "alerts", label: "Statistical alerts", description: "Mean, sample standard deviation, warning and alert levels." },
  { id: "mapping", label: "Workbook mapping", description: "C208B, DHC8 and operator field-parity governance." },
  { id: "reports", label: "Programme reports", description: "Configurable controlled layouts and retained outputs." },
];

const ReliabilityWorkbookParityWorkspace: React.FC = () => {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const basePath = `/maintenance/${encodeURIComponent(amoCode)}/reliability`;
  const [section, setSection] = useState<WorkspaceSection>("registers");
  const [catalog, setCatalog] = useState<DatasetDefinition[]>([]);
  const [aircraft, setAircraft] = useState<AircraftRead[]>([]);
  const [activeDataset, setActiveDataset] = useState<WorkbookDatasetCode>("AU");
  const [records, setRecords] = useState<WorkbookRecord[]>([]);
  const [page, setPage] = useState(0);
  const [oosMetrics, setOosMetrics] = useState<OosMetrics | null>(null);
  const [alerts, setAlerts] = useState<StatisticalAlert[]>([]);
  const [parity, setParity] = useState<ParityRow[]>([]);
  const [layouts, setLayouts] = useState<ReportLayout[]>([]);
  const [reports, setReports] = useState<ReportSnapshot[]>([]);
  const [initialLoading, setInitialLoading] = useState(true);
  const [sectionLoading, setSectionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadRecords = useCallback(async () => {
    setSectionLoading(true);
    try {
      const params = new URLSearchParams({ dataset_code: activeDataset, limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) });
      const rows = await apiRequest<WorkbookRecord[]>(`/reliability/workbook-parity/records?${params.toString()}`, { cacheTtlMs: 0 });
      setRecords(rows);
      if (activeDataset === "OOS") {
        const metrics = await apiRequest<OosMetrics>(`/reliability/workbook-parity/oos-metrics?period_start=${startOfRollingYear()}&period_end=${today()}`, { cacheTtlMs: 0 });
        setOosMetrics(metrics);
      } else {
        setOosMetrics(null);
      }
    } finally {
      setSectionLoading(false);
    }
  }, [activeDataset, page]);

  const loadAlerts = useCallback(async () => {
    setSectionLoading(true);
    try {
      setAlerts(await apiRequest<StatisticalAlert[]>("/reliability/workbook-parity/statistical-alerts?limit=250", { cacheTtlMs: 0 }));
    } finally {
      setSectionLoading(false);
    }
  }, []);

  const loadParity = useCallback(async () => {
    setSectionLoading(true);
    try {
      setParity(await apiRequest<ParityRow[]>("/reliability/workbook-parity/parity", { cacheTtlMs: 0 }));
    } finally {
      setSectionLoading(false);
    }
  }, []);

  const loadReports = useCallback(async () => {
    setSectionLoading(true);
    try {
      const [layoutRows, reportRows] = await Promise.all([
        apiRequest<ReportLayout[]>("/reliability/workbook-parity/report-layouts", { cacheTtlMs: 0 }),
        apiRequest<ReportSnapshot[]>("/reliability/workbook-parity/reports?limit=250", { cacheTtlMs: 0 }),
      ]);
      setLayouts(layoutRows);
      setReports(reportRows);
    } finally {
      setSectionLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setInitialLoading(true);
      setError(null);
      try {
        const [catalogRows, aircraftRows] = await Promise.all([
          apiRequest<DatasetDefinition[]>("/reliability/workbook-parity/catalog", { cacheTtlMs: 5 * 60_000, persistCache: true }),
          listAircraft({ is_active: true }),
        ]);
        if (!active) return;
        setCatalog(catalogRows);
        setAircraft(aircraftRows.filter((item) => item.is_active !== false && String(item.status || "ACTIVE").toUpperCase() !== "INACTIVE"));
      } catch (caught: unknown) {
        if (active) setError(caught instanceof Error ? caught.message : "The workbook-parity workspace could not be initialized.");
      } finally {
        if (active) setInitialLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (initialLoading || error) return;
    const load = section === "registers" ? loadRecords : section === "alerts" ? loadAlerts : section === "mapping" ? loadParity : loadReports;
    load().catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "Reliability workbook data could not be loaded."));
  }, [error, initialLoading, loadAlerts, loadParity, loadRecords, loadReports, section]);

  const refresh = async () => {
    setError(null);
    const load = section === "registers" ? loadRecords : section === "alerts" ? loadAlerts : section === "mapping" ? loadParity : loadReports;
    try {
      await load();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The workspace could not be refreshed.");
    }
  };

  const changeDataset = (value: WorkbookDatasetCode) => {
    setActiveDataset(value);
    setPage(0);
  };

  return <DepartmentLayout amoCode={amoCode} activeDepartment="reliability">
    <main className="reliability-v2 rel-wb">
      <header className="reliability-v2__header rel-wb__header">
        <div>
          <p className="reliability-v2__eyebrow">Excel replacement and controlled evidence</p>
          <h1>Reliability programme registers</h1>
          <p>Typed operational registers, statistical alert calculations, workbook field parity and configurable retained reports.</p>
        </div>
        <div className="reliability-v2__actions">
          <Link className="btn btn-secondary" to={basePath}>Reliability analytics</Link>
          <Link className="btn btn-secondary" to={`${basePath}/operations`}>Operational sources</Link>
          <Link className="btn btn-secondary" to={`${basePath}/events`}>Occurrence register</Link>
          <button type="button" className="btn btn-primary" disabled={sectionLoading || initialLoading} onClick={() => void refresh()}>{sectionLoading ? "Refreshing…" : "Refresh evidence"}</button>
        </div>
      </header>

      <nav className="rel-wb__section-nav" aria-label="Workbook parity sections">
        {SECTIONS.map((item) => <button key={item.id} type="button" className={section === item.id ? "is-active" : ""} onClick={() => { setSection(item.id); setError(null); }}><strong>{item.label}</strong><span>{item.description}</span></button>)}
      </nav>

      {error && <div className="reliability-v2__error rel-wb__global-error" role="alert"><strong>Workbook-parity evidence could not be completed.</strong><span>{error}</span><button type="button" className="btn btn-secondary" onClick={() => void refresh()}>Retry</button></div>}
      {initialLoading && <div className="reliability-v2__loading" role="status">Loading typed workbook definitions and the active tenant fleet…</div>}

      {!initialLoading && !error && section === "registers" && <ReliabilityWorkbookRegisters catalog={catalog} aircraft={aircraft} activeDataset={activeDataset} setActiveDataset={changeDataset} records={records} loading={sectionLoading} page={page} setPage={setPage} reload={loadRecords} oosMetrics={oosMetrics} />}
      {!initialLoading && !error && section === "alerts" && <ReliabilityWorkbookStatisticalAlerts catalog={catalog} aircraft={aircraft} alerts={alerts} loading={sectionLoading} reload={loadAlerts} />}
      {!initialLoading && !error && section === "mapping" && <ReliabilityWorkbookMappingGovernance catalog={catalog} parity={parity} loading={sectionLoading} reload={loadParity} />}
      {!initialLoading && !error && section === "reports" && <ReliabilityWorkbookReportGovernance catalog={catalog} aircraft={aircraft} layouts={layouts} reports={reports} loading={sectionLoading} reload={loadReports} />}
    </main>
  </DepartmentLayout>;
};

export default ReliabilityWorkbookParityWorkspace;
