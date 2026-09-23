import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { addQmsInvestigationEntry, createQmsAssuranceCase, listQmsAssuranceCases, type QmsAssuranceCase, type QmsInvestigationEntryType, type QmsInvestigationMethod } from "../../../services/qmsAssuranceCases";
import AnalysisEditor, { AnalysisMarkdown } from "./AnalysisEditor";

/* eslint-disable-next-line react-refresh/only-export-components -- shared immutable analysis taxonomy. */
export const QUALITY_PRINCIPLES = ["Customer focus", "Leadership", "Engagement of people", "Process approach", "Improvement", "Evidence-based decision making", "Relationship management"];
export default function AnalysisInvestigation({ tenant, caseId, study, onSelect, onSaved, references, canEdit }: {
  tenant: string; caseId: string; study?: QmsAssuranceCase; onSelect: (id: string) => void;
  onSaved: () => void; references: Record<string, unknown>[]; canEdit: boolean;
}) {
  const [offset, setOffset] = useState(0);
  const cases = useQuery({ queryKey: ["analysis-cases", tenant, offset], queryFn: ({ signal }) => listQmsAssuranceCases(tenant, { limit: 50, offset }, signal), staleTime: 15000 });
  const [title, setTitle] = useState("");
  const [method, setMethod] = useState<QmsInvestigationMethod>("FIVE_WHYS");
  const [kind, setKind] = useState<QmsInvestigationEntryType>("HYPOTHESIS");
  const [category, setCategory] = useState("Process");
  const [principle, setPrinciple] = useState("");
  const [standard, setStandard] = useState("");
  const [clause, setClause] = useState("");
  const [parent, setParent] = useState("");
  const [statement, setStatement] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const closed = study?.status === "CLOSED" || study?.status === "CANCELLED";
  const entries = study?.investigation_entries ?? [];
  const create = async () => {
    setBusy(true); setMessage("");
    try {
      const result = await createQmsAssuranceCase(tenant, { case_type: "INVESTIGATION", title: title.trim(), description: "Quality analysis investigation", source_references: references });
      onSelect(result.id); setTitle(""); await cases.refetch(); setMessage("Investigation created and retained in Assurance Cases.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not create investigation."); }
    finally { setBusy(false); }
  };
  const save = async () => {
    setBusy(true); setMessage("");
    try {
      const basis = standard.trim() || clause.trim() || principle ? [{ type: "ANALYST_FRAMEWORK_MAPPING", standard_edition: standard.trim(), clause: clause.trim(), principle, status: "ANALYST_MAPPING_NOT_CERTIFICATION" }] : [];
      await addQmsInvestigationEntry(tenant, caseId, { method, entry_type: kind, sequence_no: entries.length + 1,
        category, statement, prompt: method === "FIVE_WHYS" ? "Why did the preceding condition occur?" : "What evidence supports this contributing factor?",
        parent_entry_id: parent || undefined, evidence_references: [...references, ...basis] });
      setStatement(""); onSaved(); setMessage("Statement saved with its author, evidence references and timestamp.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Statement could not be saved."); }
    finally { setBusy(false); }
  };
  return <div className="qa-analysis-stack">
    <section className="qa-analysis-card"><h2>Qualitative investigation</h2><p>Record facts, test hypotheses, then document supported causal conclusions. Entries are retained in Assurance Cases; corrections are appended to preserve attribution.</p>
      <div className="qa-analysis-form-grid"><label>Open investigation<select value={caseId} onChange={e => { onSelect(e.target.value); setParent(""); }}><option value="">Select an assurance case</option>{study && !cases.data?.items.some(item => item.id === study.id) && <option value={study.id}>{study.case_ref} · {study.title}</option>}{cases.data?.items.map(item => <option key={item.id} value={item.id}>{item.case_ref} · {item.title}</option>)}</select></label>
      {canEdit && <label>New investigation title<input value={title} maxLength={255} onChange={e => setTitle(e.target.value)} /></label>}</div>
      <div className="qa-analysis-actions"><button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous cases</button><button disabled={!cases.data?.has_more} onClick={() => setOffset(offset + 50)}>More cases</button>{canEdit && <button disabled={busy || title.trim().length < 3} onClick={() => void create()}>Create investigation</button>}</div>
      {cases.isError && <p role="alert">Investigations could not be loaded. <button onClick={() => void cases.refetch()}>Retry</button></p>}
    </section>
    {study && <section className="qa-analysis-card"><h2>{study.case_ref} · {study.title}</h2><p>{study.status.replaceAll("_", " ")} · {references.length} evidence references selected for the next statement.</p>
      {canEdit && !closed && <><div className="qa-analysis-form-grid">
        <label>Method<select value={method} onChange={e => setMethod(e.target.value as QmsInvestigationMethod)}><option value="FIVE_WHYS">Five Whys</option><option value="ISHIKAWA">Fishbone / Ishikawa</option><option value="CAUSAL_FACTOR">Thematic / causal factor analysis</option><option value="BARRIER_ANALYSIS">Barrier analysis</option><option value="CHANGE_ANALYSIS">Change analysis</option><option value="HUMAN_ORGANIZATIONAL">Human and organisational factors</option></select></label>
        <label>Statement status<select value={kind} onChange={e => setKind(e.target.value as QmsInvestigationEntryType)}><option value="FACT">Recorded fact</option><option value="HYPOTHESIS">Hypothesis — needs verification</option><option value="CAUSAL_CONCLUSION">Supported causal conclusion</option></select></label>
        <label>Theme / fishbone branch<input list="qa-cause-categories" value={category} maxLength={80} onChange={e => setCategory(e.target.value)} /><datalist id="qa-cause-categories">{["People", "Process", "Equipment", "Materials", "Measurement", "Environment", "Management"].map(value => <option key={value} value={value} />)}</datalist></label>
        <label>Parent / preceding why<select value={parent} onChange={e => setParent(e.target.value)}><option value="">Problem statement / no parent</option>{entries.map(entry => <option key={entry.id} value={entry.id}>{entry.sequence_no}. {entry.statement.slice(0, 90)}</option>)}</select></label>
      </div>
      <details><summary>Map to a quality principle or documented requirement</summary><p>The seven principles guide quality management. Five Whys and the seven quality tools are analysis methods. Neither is a compliance score. Specify the edition and clause you actually reviewed.</p><div className="qa-analysis-form-grid">
        <label>Quality principle<select value={principle} onChange={e => setPrinciple(e.target.value)}><option value="">No mapping</option>{QUALITY_PRINCIPLES.map(item => <option key={item}>{item}</option>)}</select></label>
        <label>Standard / manual and edition<input value={standard} maxLength={255} onChange={e => setStandard(e.target.value)} placeholder="Exact controlled title and edition" /></label>
        <label>Clause / section<input value={clause} maxLength={255} onChange={e => setClause(e.target.value)} /></label>
      </div><p><a href="https://www.iso.org/quality-management/principles" target="_blank" rel="noreferrer">ISO principles</a> · <a href="https://asq.org/quality-resources/seven-basic-quality-tools" target="_blank" rel="noreferrer">ASQ quality tools</a></p></details>
      <AnalysisEditor label="Investigation statement" value={statement} onChange={setStatement} disabled={busy} />
      <button disabled={busy || statement.trim().length < 3 || (kind !== "HYPOTHESIS" && !references.length)} onClick={() => void save()}>{busy ? "Saving…" : "Save statement with evidence"}</button>
      {kind !== "HYPOTHESIS" && !references.length && <p>Select a finding or a DMS reference before recording a fact or conclusion.</p>}</>}
      {closed && <p>This investigation is closed. Open the governed case workflow to review its lifecycle.</p>}
      <div className="qa-analysis-evidence-list">{entries.map(entry => <article key={entry.id}><header><strong>{entry.sequence_no}. {entry.category || entry.method.replaceAll("_", " ")}</strong><span>{entry.entry_type.replaceAll("_", " ")}</span></header><small>{entry.method.replaceAll("_", " ")} · {new Date(entry.created_at).toLocaleString()}{entry.parent_entry_id ? ` · follows statement ${entries.find(item => item.id === entry.parent_entry_id)?.sequence_no ?? entry.parent_entry_id}` : ""}</small><AnalysisMarkdown text={entry.statement} /><details><summary>{entry.evidence_references.length} supporting references</summary><pre>{JSON.stringify(entry.evidence_references, null, 2)}</pre></details></article>)}</div>
      {!entries.length && <p>No statements have been recorded for this investigation.</p>}
    </section>}
    {message && <p role="status" className="qa-analysis-notice">{message}</p>}
  </div>;
}
