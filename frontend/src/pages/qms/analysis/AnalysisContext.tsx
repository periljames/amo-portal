import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getDocumentationTree } from "../../../services/documentation";
import { assistDocumentation, type DocumentationAssistResponse, type DocumentationAssistSource } from "../../../services/documentationAssistant";
import type { DocumentEvidenceReference } from "../../../services/documentControlEvidence";
import DocumentEvidencePicker from "../../documentControl/DocumentEvidencePicker";
import { AnalysisMarkdown } from "./AnalysisEditor";

export type AnalysisDocumentContext = { manualId: string; revisionId: string; title: string };
export default function AnalysisContext({ tenant, suggestedQuery, document, onDocument, selected, onSelected, attachments, onAttachments, answer, onAnswer, canEdit }: {
  tenant: string; suggestedQuery: string; document: AnalysisDocumentContext; onDocument: (value: AnalysisDocumentContext) => void;
  selected: DocumentationAssistSource[]; onSelected: (value: DocumentationAssistSource[]) => void;
  attachments: DocumentEvidenceReference[]; onAttachments: (value: DocumentEvidenceReference[]) => void;
  answer: DocumentationAssistResponse | null; onAnswer: (value: DocumentationAssistResponse | null) => void; canEdit: boolean;
}) {
  const tree = useQuery({ queryKey: ["analysis-documentation", tenant], queryFn: () => getDocumentationTree(tenant), staleTime: 60000, retry: false });
  const [query, setQuery] = useState(suggestedQuery.slice(0, 500));
  const [ai, setAi] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [results, setResults] = useState<DocumentationAssistResponse | null>(null);
  const serial = useRef(0);
  useEffect(() => () => { serial.current += 1; }, []);
  const search = async (assisted: boolean) => {
    const request = ++serial.current;
    setBusy(true); setError("");
    try {
      const result = await assistDocumentation(tenant, { query: query.trim(), mode: assisted ? "ASSIST" : "SEARCH", manual_id: document.manualId || undefined, revision_id: document.revisionId || undefined, limit: 8 });
      if (request !== serial.current) return;
      setResults(result);
      if (assisted) onAnswer(result);
    } catch (caught) { if (request === serial.current) setError(caught instanceof Error ? caught.message : "Document context unavailable."); }
    finally { if (request === serial.current) setBusy(false); }
  };
  // Deterministic retrieval only. This never calls an external AI provider.
  useEffect(() => {
    if (tree.isSuccess && suggestedQuery.trim().length >= 2 && !results && !busy) void search(false);
    // One initial retrieval when authorised DMS metadata becomes available.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tree.isSuccess]);
  const documents = tree.data?.items.filter(item => item.manual_id) ?? [];
  return <div className="qa-analysis-stack"><section className="qa-analysis-card"><h2>Controlled document context</h2>
    <p>Retrieve documents through DMS access controls. Each selected reference keeps its document, revision, section and source excerpt. Counts and severity always come from QMS records.</p>
    {tree.isError && <p role="alert">DMS context is unavailable or not enabled for your account. QMS analysis remains available. <button onClick={() => void tree.refetch()}>Retry DMS</button></p>}
    <label>Reference manual / document<select value={document.manualId} onChange={event => {
      const node = documents.find(item => item.manual_id === event.target.value);
      onDocument({ manualId: node?.manual_id ?? "", revisionId: node?.document?.current_published_revision_id ?? "", title: node ? `${node.code} · ${node.title}` : "" });
      onAttachments([]); setResults(null);
    }}><option value="">All accessible effective documents</option>{documents.map(node => <option key={node.id} value={node.manual_id!}>{node.code} · {node.title}{node.document?.current_published_revision_id ? "" : " · no effective revision"}</option>)}</select></label>
    {document.manualId && !document.revisionId && <p>No effective revision is recorded for this document. A retained attachment is evidence, not an approved manual revision.</p>}
    <label>Requirement or documentation question<textarea value={query} maxLength={500} rows={3} onChange={event => setQuery(event.target.value)} /></label>
    <div className="qa-analysis-actions"><button disabled={busy || query.trim().length < 2 || tree.isError} onClick={() => void search(false)}>Search controlled sources</button><button disabled={!suggestedQuery} onClick={() => setQuery(suggestedQuery.slice(0, 500))}>Use selected finding context</button></div>
    <label className="qa-analysis-check"><input type="checkbox" checked={ai} onChange={event => setAi(event.target.checked)} />Enable AI-assisted documentation interpretation</label>
    {ai && <div className="qa-analysis-notice"><p>On request, your question and authorised source excerpts may be sent to the tenant-configured AI provider. Suggestions are advisory and require review. AI does not calculate the metrics or approve findings.</p><button disabled={busy || query.trim().length < 2 || tree.isError} onClick={() => void search(true)}>{busy ? "Retrieving…" : "Ask using controlled context"}</button></div>}
    {error && <p role="alert">{error}</p>}
    {answer && <article className="qa-analysis-notice"><h3>{answer.provider_mode === "OPENAI" ? "AI suggestion — unreviewed" : "Deterministic documentation response"}</h3><AnalysisMarkdown text={answer.answer} /><p>{answer.warning}</p><small>Citations: {answer.citations.join(", ") || "None returned"}</small><button onClick={() => onAnswer(null)}>Exclude response from report</button></article>}
    <div className="qa-analysis-evidence-list">{results?.sources.map(source => <article key={source.id}><header><strong>{source.code} · {source.title}</strong><label className="qa-analysis-check"><input type="checkbox" checked={selected.some(item => item.id === source.id)} onChange={event => onSelected(event.target.checked ? [...selected, source] : selected.filter(item => item.id !== source.id))} />Use as reference</label></header><p>{source.snippet}</p><small>Revision {source.revision_id} · {source.heading || "Document"}{source.page_number ? ` · page ${source.page_number}` : ""}</small><p><a href={source.reader_url} target="_blank" rel="noreferrer">Open controlled source</a></p></article>)}</div>
    {results && !results.sources.length && <p>No authorised indexed sources matched. Select a document or revise the search. No document context has been inferred.</p>}
  </section>
  {document.manualId && canEdit && <section className="qa-analysis-card"><h2>Upload reference evidence</h2><DocumentEvidencePicker key={document.manualId} tenant={tenant} manualId={document.manualId} revisionId={document.revisionId || null} category="EXTERNAL_SOURCE" purpose="Quality analysis reference" value={attachments} onChange={onAttachments} help="Retain supporting files in DMS with a checksum. Attachments are not automatically indexed or treated as effective controlled requirements. Select them as references and inspect their contents." /></section>}
  <section className="qa-analysis-card"><h2>Selected document references ({selected.length})</h2>{selected.map(source => <p key={source.id}>{source.code} · {source.heading || source.title} · revision {source.revision_id} <button onClick={() => onSelected(selected.filter(item => item.id !== source.id))}>Remove</button></p>)}{!selected.length && <p>No DMS source has been selected.</p>}</section>
  </div>;
}
