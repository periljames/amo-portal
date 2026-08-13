import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link2, Plus, Search, X } from "lucide-react";

import {
  createDocumentChangeRequest,
  type DocumentDetailResponse,
} from "../../services/documentControl";
import {
  getDocumentIntegrationCatalog,
  searchDocumentIntegrationCatalog,
  type DocumentIntegrationCatalogItem,
  type DocumentIntegrationCatalogModule,
} from "../../services/documentControlIntegrationCatalog";


type Props = {
  detail: DocumentDetailResponse;
  tenant: string;
  onChanged: () => void;
};

export default function DocumentControlChangeRequestActions({ detail, tenant, onChanged }: Props) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("NORMAL");
  const [dueAt, setDueAt] = useState("");
  const [trainingImpact, setTrainingImpact] = useState(false);
  const [qmsBlocking, setQmsBlocking] = useState(false);
  const [modules, setModules] = useState<DocumentIntegrationCatalogModule[]>([]);
  const [sourceModule, setSourceModule] = useState("");
  const [sourceTable, setSourceTable] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<DocumentIntegrationCatalogItem[]>([]);
  const [selected, setSelected] = useState<DocumentIntegrationCatalogItem | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setCatalogLoading(true);
    void getDocumentIntegrationCatalog(tenant)
      .then((payload) => { if (active) setModules(payload.modules.filter((item) => item.tables.length)); })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "Governed source catalogue could not be loaded."); })
      .finally(() => { if (active) setCatalogLoading(false); });
    return () => { active = false; };
  }, [tenant]);

  const tables = useMemo(() => modules.find((item) => item.module === sourceModule)?.tables || [], [modules, sourceModule]);

  const chooseModule = (value: string) => {
    setSourceModule(value);
    setSourceTable("");
    setQuery("");
    setResults([]);
    setSelected(null);
  };

  const search = async () => {
    if (!sourceModule || !sourceTable) return;
    setSearching(true);
    setError("");
    try {
      const payload = await searchDocumentIntegrationCatalog(tenant, {
        sourceModule,
        sourceTable,
        q: query,
        limit: 25,
      });
      setResults(payload.items);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Governed source records could not be searched.");
    } finally {
      setSearching(false);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await createDocumentChangeRequest(tenant, {
        manual_id: detail.document.id,
        revision_id: detail.document.latest_revision?.id || null,
        source_module: selected?.source_module || "DOCUMENT_CONTROL",
        source_entity_type: selected?.source_table || null,
        source_entity_id: selected?.id || null,
        title: title.trim(),
        description: description.trim(),
        priority,
        due_at: dueAt ? new Date(dueAt).toISOString() : null,
        impact: selected ? { source_label: selected.label, source_status: selected.status } : {},
        training_impact_required: trainingImpact,
        qms_blocking: qmsBlocking,
      });
      setTitle("");
      setDescription("");
      setSelected(null);
      setResults([]);
      setQuery("");
      onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The controlled change request could not be created.");
    } finally {
      setBusy(false);
    }
  };

  return <form className="dc-form" onSubmit={submit} data-testid="document-control-change-request-actions">
    <label><span>Priority</span><select value={priority} onChange={(event) => setPriority(event.target.value)}><option>LOW</option><option>NORMAL</option><option>HIGH</option><option>CRITICAL</option></select></label>
    <label><span>Due date</span><input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} /></label>
    <label className="wide"><span>Change title</span><input value={title} onChange={(event) => setTitle(event.target.value)} required /></label>
    <label className="wide"><span>Description and required outcome</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} required /></label>

    <fieldset className="wide dms-source-picker">
      <legend>Governed source record <small>optional</small></legend>
      <p>Link this change to the actual audit, CAR, training, planning, maintenance, fleet, stores or technical-record item that triggered it. Do not paste database IDs.</p>
      <div className="dc-grid">
        <label><span>Source module</span><select disabled={catalogLoading} value={sourceModule} onChange={(event) => chooseModule(event.target.value)}><option value="">No linked portal source</option>{modules.map((item) => <option key={item.module} value={item.module}>{item.module.replaceAll("_", " ")}</option>)}</select></label>
        <label><span>Record type</span><select disabled={!sourceModule} value={sourceTable} onChange={(event) => { setSourceTable(event.target.value); setSelected(null); setResults([]); }}><option value="">Select governed record type</option>{tables.map((table) => <option key={table.name} value={table.name}>{table.entity_type.replaceAll("_", " ")}</option>)}</select></label>
        <label className="wide"><span>Find source record</span><div className="dc-inline-input"><input disabled={!sourceTable} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Reference, code, title, name, registration…" /><button type="button" className="dc-button" disabled={!sourceTable || searching} onClick={() => void search()}><Search size={14} /> {searching ? "Searching…" : "Search"}</button></div></label>
      </div>
      {selected ? <div className="dc-callout dc-callout--success"><Link2 size={15} /><div><strong>{selected.label}</strong><div>{selected.source_module} · {selected.source_table} · {selected.status}</div></div><button type="button" className="dc-button" onClick={() => setSelected(null)}><X size={13} /> Clear</button></div> : null}
      {!selected && results.length ? <div className="dms-source-picker__results">{results.map((item) => <button key={`${item.source_table}:${item.id}`} type="button" onClick={() => setSelected(item)}><strong>{item.label}</strong><span>{item.status} · {item.source_table.replaceAll("_", " ")}</span></button>)}</div> : null}
    </fieldset>

    <label><span><input type="checkbox" checked={trainingImpact} onChange={(event) => setTrainingImpact(event.target.checked)} /> Training impact required</span></label>
    <label><span><input type="checkbox" checked={qmsBlocking} onChange={(event) => setQmsBlocking(event.target.checked)} /> QMS item blocks publication</span></label>
    {error ? <div className="dc-form__error" role="alert">{error}</div> : null}
    <div className="dc-form__actions"><button className="dc-button dc-button--primary" type="submit" disabled={busy || !title.trim() || !description.trim()}><Plus size={14} /> {busy ? "Creating…" : "Create change request"}</button></div>
  </form>;
}
