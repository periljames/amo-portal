import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Globe2, Search, Target, X } from "lucide-react";

import {
  createApplicabilityRule,
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

export default function DocumentControlApplicabilityActions({ detail, tenant, onChanged }: Props) {
  const [ruleType, setRuleType] = useState("INCLUDE");
  const [scopeMode, setScopeMode] = useState<"GLOBAL" | "TARGETED">("GLOBAL");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [effectiveTo, setEffectiveTo] = useState("");
  const [modules, setModules] = useState<DocumentIntegrationCatalogModule[]>([]);
  const [sourceModule, setSourceModule] = useState("");
  const [sourceTable, setSourceTable] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<DocumentIntegrationCatalogItem[]>([]);
  const [selected, setSelected] = useState<DocumentIntegrationCatalogItem | null>(null);
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [searching, setSearching] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoadingCatalog(true);
    void getDocumentIntegrationCatalog(tenant)
      .then((payload) => { if (active) setModules(payload.modules.filter((item) => item.tables.length)); })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "Applicability target catalogue could not be loaded."); })
      .finally(() => { if (active) setLoadingCatalog(false); });
    return () => { active = false; };
  }, [tenant]);

  const tables = useMemo(() => modules.find((item) => item.module === sourceModule)?.tables || [], [modules, sourceModule]);

  const chooseMode = (value: "GLOBAL" | "TARGETED") => {
    setScopeMode(value);
    if (value === "GLOBAL") {
      setSourceModule("");
      setSourceTable("");
      setSelected(null);
      setResults([]);
      setQuery("");
    }
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
      setError(caught instanceof Error ? caught.message : "Applicability targets could not be searched.");
    } finally {
      setSearching(false);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (scopeMode === "TARGETED" && !selected) {
      setError("Select the governed portal record this applicability rule targets.");
      return;
    }
    if (effectiveFrom && effectiveTo && effectiveTo < effectiveFrom) {
      setError("Applicability end date cannot precede the start date.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await createApplicabilityRule(tenant, {
        manual_id: detail.document.id,
        revision_id: detail.document.latest_revision?.id || null,
        rule_type: ruleType,
        target_type: selected?.source_table || "GLOBAL",
        target_id: selected?.id || null,
        target_value: selected?.label || "All applicable users and operations",
        effective_from: effectiveFrom || null,
        effective_to: effectiveTo || null,
        source: selected ? `PORTAL:${selected.source_module}` : "DOCUMENT_CONTROL",
        criteria: selected ? {
          source_module: selected.source_module,
          source_table: selected.source_table,
          status_snapshot: selected.status,
        } : {},
      });
      setSelected(null);
      setResults([]);
      setQuery("");
      onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The applicability rule could not be created.");
    } finally {
      setBusy(false);
    }
  };

  return <form className="dc-form" onSubmit={submit} data-testid="document-control-applicability-actions">
    <div className="dc-callout"><Target size={17} /><div><strong>Define controlled applicability</strong><div>Use Global scope or select the live portal record that the inclusion/exclusion applies to. Target database IDs are never typed manually.</div></div></div>
    <label><span>Rule</span><select value={ruleType} onChange={(event) => setRuleType(event.target.value)}><option value="INCLUDE">Include</option><option value="EXCLUDE">Exclude</option></select></label>
    <label><span>Scope</span><select value={scopeMode} onChange={(event) => chooseMode(event.target.value as "GLOBAL" | "TARGETED")}><option value="GLOBAL">Global / all applicable operations</option><option value="TARGETED">Specific governed portal record</option></select></label>
    <label><span>Effective from</span><input type="date" value={effectiveFrom} onChange={(event) => setEffectiveFrom(event.target.value)} /></label>
    <label><span>Effective to</span><input type="date" value={effectiveTo} onChange={(event) => setEffectiveTo(event.target.value)} /></label>

    {scopeMode === "GLOBAL" ? <div className="dc-callout wide"><Globe2 size={16} /><div><strong>Global applicability</strong><div>This rule applies without a target identifier. The server stores a canonical GLOBAL target.</div></div></div> : <fieldset className="wide dms-source-picker">
      <legend>Verified applicability target</legend>
      <div className="dc-grid">
        <label><span>Portal module</span><select disabled={loadingCatalog} value={sourceModule} onChange={(event) => { setSourceModule(event.target.value); setSourceTable(""); setSelected(null); setResults([]); }}><option value="">Select portal module</option>{modules.map((item) => <option key={item.module} value={item.module}>{item.module.replaceAll("_", " ")}</option>)}</select></label>
        <label><span>Governed record type</span><select disabled={!sourceModule} value={sourceTable} onChange={(event) => { setSourceTable(event.target.value); setSelected(null); setResults([]); }}><option value="">Select governed record type</option>{tables.map((table) => <option key={table.name} value={table.name}>{table.entity_type.replaceAll("_", " ")}</option>)}</select></label>
        <label className="wide"><span>Find target</span><div className="dc-inline-input"><input disabled={!sourceTable} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Aircraft registration, base, department, person, work item, fleet record…" /><button type="button" className="dc-button" disabled={!sourceTable || searching} onClick={() => void search()}><Search size={14} /> {searching ? "Searching…" : "Search"}</button></div></label>
      </div>
      {selected ? <div className="dc-callout dc-callout--success"><Target size={15} /><div><strong>{selected.label}</strong><div>{selected.source_module} · {selected.source_table} · {selected.status}</div></div><button type="button" className="dc-button" onClick={() => setSelected(null)}><X size={13} /> Clear</button></div> : null}
      {!selected && results.length ? <div className="dms-source-picker__results">{results.map((item) => <button key={`${item.source_table}:${item.id}`} type="button" onClick={() => setSelected(item)}><strong>{item.label}</strong><span>{item.status} · {item.source_table.replaceAll("_", " ")}</span></button>)}</div> : null}
    </fieldset>}

    {error ? <div className="dc-form__error" role="alert">{error}</div> : null}
    <div className="dc-form__actions"><button className="dc-button dc-button--primary" type="submit" disabled={busy || (scopeMode === "TARGETED" && !selected)}><Target size={14} /> {busy ? "Saving…" : "Create applicability rule"}</button></div>
  </form>;
}
