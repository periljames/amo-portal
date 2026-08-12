import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link2, Search } from "lucide-react";

import {
  createIntegrationLink,
  type DocumentDetailResponse,
} from "../../services/documentControl";
import {
  getDocumentIntegrationCatalog,
  searchDocumentIntegrationCatalog,
  type DocumentIntegrationCatalogItem,
  type DocumentIntegrationCatalogModule,
} from "../../services/documentControlIntegrationCatalog";
import { DocumentControlEmpty } from "./DocumentControlShell";

const RELATION_TYPES = [
  "CHANGE_DRIVER",
  "BLOCKER",
  "TRAINING_IMPACT",
  "APPLICABILITY",
  "USED_BY",
  "EVIDENCE",
  "SOURCE",
  "COMPLIANCE",
] as const;

export default function DocumentControlIntegrationActions({
  detail,
  tenant,
  onChanged,
}: {
  detail: DocumentDetailResponse;
  tenant: string;
  onChanged: () => void;
}) {
  const [catalog, setCatalog] = useState<DocumentIntegrationCatalogModule[]>([]);
  const [sourceModule, setSourceModule] = useState("");
  const [sourceTable, setSourceTable] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<DocumentIntegrationCatalogItem[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [relationType, setRelationType] = useState<(typeof RELATION_TYPES)[number]>("USED_BY");
  const [blocking, setBlocking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void getDocumentIntegrationCatalog(tenant)
      .then((response) => {
        if (!active) return;
        setCatalog(response.modules);
      })
      .catch((caught) => {
        if (active) setError(caught instanceof Error ? caught.message : "The integration catalogue could not be loaded.");
      });
    return () => { active = false; };
  }, [tenant]);

  const moduleEntry = useMemo(() => catalog.find((item) => item.module === sourceModule), [catalog, sourceModule]);
  const selectedRecord = useMemo(() => results.find((item) => item.id === selectedId), [results, selectedId]);

  const chooseModule = (value: string) => {
    setSourceModule(value);
    setSourceTable("");
    setResults([]);
    setSelectedId("");
    setError("");
  };

  const chooseTable = (value: string) => {
    setSourceTable(value);
    setResults([]);
    setSelectedId("");
    setError("");
  };

  const search = async () => {
    if (!sourceModule || !sourceTable) return;
    setSearching(true);
    setError("");
    try {
      const response = await searchDocumentIntegrationCatalog(tenant, {
        sourceModule,
        sourceTable,
        q: query,
        limit: 25,
      });
      setResults(response.items);
      setSelectedId(response.items[0]?.id || "");
    } catch (caught) {
      setResults([]);
      setSelectedId("");
      setError(caught instanceof Error ? caught.message : "Integration records could not be searched.");
    } finally {
      setSearching(false);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedRecord) return;
    setBusy(true);
    setError("");
    try {
      await createIntegrationLink(tenant, {
        manual_id: detail.document.id,
        revision_id: detail.document.latest_revision?.id || null,
        change_request_id: null,
        workflow_id: detail.workflows[0]?.id || null,
        source_module: selectedRecord.source_module,
        entity_type: selectedRecord.entity_type,
        entity_id: selectedRecord.id,
        relation_type: relationType,
        blocking,
        status_snapshot: selectedRecord.status,
        metadata: { source_table: selectedRecord.source_table },
      });
      setQuery("");
      setResults([]);
      setSelectedId("");
      onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The governed module relationship could not be created.");
    } finally {
      setBusy(false);
    }
  };

  if (!catalog.length && !error) {
    return <DocumentControlEmpty icon={Link2} title="Loading governed module records" message="The DMS is loading tenant-scoped record sources that are safe to link." />;
  }

  return <form className="dc-form" onSubmit={submit}>
    <div className="dc-callout"><Link2 size={17} /><div><strong>Link a real portal record</strong><div>Select the source module and authoritative record. The server re-verifies tenant ownership and live status before saving the relationship.</div></div></div>
    <label><span>Source module</span><select value={sourceModule} onChange={(event) => chooseModule(event.target.value)} required><option value="">Select portal module</option>{catalog.filter((item) => item.tables.length).map((item) => <option key={item.module} value={item.module}>{item.module.replaceAll("_", " ")}</option>)}</select></label>
    <label><span>Record type</span><select value={sourceTable} onChange={(event) => chooseTable(event.target.value)} required disabled={!sourceModule}><option value="">Select governed record type</option>{(moduleEntry?.tables || []).map((table) => <option key={table.name} value={table.name}>{table.name.replaceAll("_", " ")}</option>)}</select></label>
    <label className="wide"><span>Find record</span><div className="dc-inline-search"><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search code, reference, title, name or other indexed identity" disabled={!sourceTable} /><button type="button" className="dc-button" onClick={() => void search()} disabled={!sourceTable || searching}><Search size={14} /> {searching ? "Searching…" : "Search"}</button></div></label>
    {sourceTable && !results.length && !searching ? <div className="wide dc-callout"><Search size={15} /><div><strong>No record selected.</strong><div>Search the selected governed table. Blank search returns the first permitted records, bounded to 25.</div></div></div> : null}
    {results.length ? <label className="wide"><span>Canonical record</span><select value={selectedId} onChange={(event) => setSelectedId(event.target.value)} required>{results.map((item) => <option key={item.id} value={item.id}>{item.label} · {item.status}</option>)}</select></label> : null}
    <label><span>Relationship</span><select value={relationType} onChange={(event) => setRelationType(event.target.value as (typeof RELATION_TYPES)[number])}>{RELATION_TYPES.map((value) => <option key={value}>{value}</option>)}</select></label>
    <label><span><input type="checkbox" checked={blocking} onChange={(event) => setBlocking(event.target.checked)} /> Blocking relationship</span><small>Use only when this linked record must block document release until its live condition is resolved.</small></label>
    {error ? <div className="dc-form__error">{error}</div> : null}
    <div className="dc-form__actions"><button type="submit" className="dc-button dc-button--primary" disabled={busy || !selectedRecord}><Link2 size={14} /> {busy ? "Verifying and linking…" : "Verify and link record"}</button></div>
  </form>;
}
