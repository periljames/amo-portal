import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  fetchAirworthiness,
  fetchDeferrals,
  fetchMaintenanceRecords,
  fetchPacks,
  fetchReconciliation,
  fetchSettings,
  fetchTechnicalAircraft,
  fetchTechnicalDashboard,
  fetchTraceability,
  updateSettings,
} from "../services/technicalRecords";

const Shell: React.FC<{ title: string; children?: React.ReactNode }> = ({ title, children }) => (
  <div className="page">
    <h1>{title}</h1>
    <nav style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
      {["/records", "/records/aircraft", "/records/logbooks", "/records/deferrals", "/records/maintenance-records", "/records/airworthiness", "/records/llp", "/records/components", "/records/reconciliation", "/records/traceability", "/records/packs", "/records/settings"].map((r) => (
        <Link key={r} to={r}>{r}</Link>
      ))}
    </nav>
    {children}
  </div>
);

export const TechnicalRecordsDashboardPage: React.FC = () => {
  const [tiles, setTiles] = useState<any[]>([]);
  useEffect(() => { fetchTechnicalDashboard().then((x) => setTiles(x.tiles)).catch(() => setTiles([])); }, []);
  return <Shell title="Technical Records Dashboard">{tiles.map((tile) => <div key={tile.key}>{tile.label}: <strong>{tile.count}</strong></div>)}</Shell>;
};

export const AircraftRecordsPage: React.FC = () => {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => { fetchTechnicalAircraft().then(setRows).catch(() => setRows([])); }, []);
  return <Shell title="Aircraft Records">{rows.map((r) => <div key={r.tail_id}><Link to={`/records/aircraft/${r.tail_id}`}>{r.tail}</Link> · {r.record_health}</div>)}</Shell>;
};

export const AircraftRecordDetailPage: React.FC = () => {
  const { tailId } = useParams();
  return <Shell title={`Aircraft ${tailId}`}><p>Tabs: Overview · Utilisation · Logbooks · Defects/Deferrals · Maintenance Events · Airworthiness · Components · Evidence · Audit Log</p></Shell>;
};

export const LogbooksPage: React.FC = () => <Shell title="Logbooks"><p>Technical Log view is available per aircraft detail.</p></Shell>;
export const LogbookByTailPage: React.FC = () => { const { tailId } = useParams(); return <Shell title={`Logbook ${tailId}`} />; };

export const DeferralsPage: React.FC = () => {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => { fetchDeferrals().then(setRows).catch(() => setRows([])); }, []);
  return <Shell title="Deferrals Register">{rows.map((r) => <div key={r.id}><Link to={`/records/deferrals/${r.id}`}>{r.defect_ref}</Link> · {r.expiry_at}</div>)}</Shell>;
};

export const DeferralDetailPage: React.FC = () => { const { deferralId } = useParams(); return <Shell title={`Deferral ${deferralId}`}><p>Includes metadata, extension history, rectification WO linkage and closure trace.</p></Shell>; };

export const MaintenanceRecordsPage: React.FC = () => {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => { fetchMaintenanceRecords().then(setRows).catch(() => setRows([])); }, []);
  return <Shell title="Maintenance Records">{rows.map((r) => <div key={r.id}><Link to={`/records/maintenance-records/${r.id}`}>{r.description}</Link></div>)}</Shell>;
};

export const MaintenanceRecordDetailPage: React.FC = () => { const { recordId } = useParams(); return <Shell title={`Maintenance Record ${recordId}`}><p>Tabs: Overview · Linked Work · Evidence · Audit Log</p></Shell>; };

export const AirworthinessPage: React.FC = () => <Shell title="Airworthiness Control"><p>Use AD and SB registers below.</p></Shell>;

const AirworthinessRegisterPage: React.FC<{ type: "ad" | "sb" }> = ({ type }) => {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => { fetchAirworthiness(type).then(setRows).catch(() => setRows([])); }, [type]);
  return <Shell title={`${type.toUpperCase()} Register`}>{rows.map((r) => <div key={r.id}><Link to={`/records/airworthiness/${type}/${r.id}`}>{r.reference}</Link> · {r.status}</div>)}</Shell>;
};

export const ADRegisterPage: React.FC = () => <AirworthinessRegisterPage type="ad" />;
export const SBRegisterPage: React.FC = () => <AirworthinessRegisterPage type="sb" />;
export const ADDetailPage: React.FC = () => { const { adId } = useParams(); return <Shell title={`AD ${adId}`} />; };
export const SBDetailPage: React.FC = () => { const { sbId } = useParams(); return <Shell title={`SB ${sbId}`} />; };

export const LLPPage: React.FC = () => <Shell title="LLP Register"><p>LLP view is provided through existing component/life tracking infrastructure.</p></Shell>;
export const ComponentsPage: React.FC = () => <Shell title="Components Register"><p>Installed components and movement history reuse existing fleet component registry.</p></Shell>;

export const ReconciliationPage: React.FC = () => {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => { fetchReconciliation().then(setRows).catch(() => setRows([])); }, []);
  return <Shell title="Reconciliation & Exceptions">{rows.map((r) => <div key={r.id}>{r.ex_type} · {r.summary} · {r.status}</div>)}</Shell>;
};

export const TraceabilityPage: React.FC = () => {
  const [data, setData] = useState<any>(null);
  useEffect(() => { fetchTraceability().then(setData).catch(() => setData(null)); }, []);
  return <Shell title="Traceability"><pre>{JSON.stringify(data, null, 2)}</pre></Shell>;
};

export const PacksPage: React.FC = () => {
  const [data, setData] = useState<any>(null);
  useEffect(() => { fetchPacks("tail").then(setData).catch(() => setData(null)); }, []);
  return <Shell title="Inspection Packs"><pre>{JSON.stringify(data, null, 2)}</pre></Shell>;
};

export const TechnicalRecordsSettingsPage: React.FC = () => {
  const [settings, setSettings] = useState<any>(null);
  useEffect(() => { fetchSettings().then(setSettings).catch(() => setSettings(null)); }, []);
  if (!settings) return <Shell title="Technical Records Settings" />;
  return <Shell title="Technical Records Settings"><button onClick={() => updateSettings(settings).then(setSettings)}>Save defaults</button><pre>{JSON.stringify(settings, null, 2)}</pre></Shell>;
};
