import React, { useMemo, useState } from "react";
import { BadgeCheck, ChevronLeft, ChevronRight, Download, FileUp, RefreshCw, RotateCw, Search, ShieldCheck, ShieldX } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import Drawer from "../shared/Drawer";
import { downloadTrainingCertificateArtifact, downloadTrainingCertificateArtifactsBatch, listTrainingCertificates } from "../../services/training";
import { batchIssueTrainingCertificates, listCertificateEligibility, listTrainingPeopleReference, reissueTrainingCertificate, revokeTrainingCertificate } from "../../services/trainingOperating";

type Props = { canIssue: boolean; canRevoke: boolean; canReissue: boolean; canExport: boolean; onOpenImport: () => void };
const PAGE_SIZE = 50;

const TrainingCertificatesWorkspace: React.FC<Props> = ({ canIssue, canRevoke, canReissue, canExport, onOpenImport }) => {
  const client = useQueryClient();
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [lifecycle, setLifecycle] = useState<{ recordId: string; action: "REVOKE" | "REISSUE"; reason: string } | null>(null);
  const [eligibilityOpen, setEligibilityOpen] = useState(false);
  const [eligibilitySearch, setEligibilitySearch] = useState("");
  const [eligibilitySelected, setEligibilitySelected] = useState<string[]>([]);
  const [issueReason, setIssueReason] = useState("Completion gates reviewed and approved for controlled batch issuance.");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const certificates = useQuery({ queryKey: ["training", "certificates", offset], queryFn: async () => { const rows = await listTrainingCertificates(undefined, { limit: PAGE_SIZE + 1, offset }); return { items: rows.slice(0, PAGE_SIZE), hasMore: rows.length > PAGE_SIZE }; } });
  const people = useQuery({ queryKey: ["training", "people-reference"], queryFn: () => listTrainingPeopleReference() });
  const eligibility = useQuery({ queryKey: ["training", "certificate-eligibility", eligibilitySearch], queryFn: () => listCertificateEligibility(eligibilitySearch), enabled: eligibilityOpen });
  const personById = useMemo(() => new Map((people.data || []).map((item) => [item.id, item])), [people.data]);
  const rows = useMemo(() => (certificates.data?.items || []).filter((row) => { const term = search.toLowerCase(); const person = personById.get(row.user_id); return !term || row.certificate_reference?.toLowerCase().includes(term) || row.course_name?.toLowerCase().includes(term) || person?.full_name.toLowerCase().includes(term) || person?.staff_code.toLowerCase().includes(term); }), [certificates.data, personById, search]);

  const runLifecycle = async () => {
    if (!lifecycle) return;
    setBusy(true); setError(null);
    try {
      if (lifecycle.action === "REVOKE") await revokeTrainingCertificate(lifecycle.recordId, lifecycle.reason);
      else await reissueTrainingCertificate(lifecycle.recordId, lifecycle.reason);
      setLifecycle(null); await client.invalidateQueries({ queryKey: ["training", "certificates"] });
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Certificate lifecycle action failed."); } finally { setBusy(false); }
  };

  const issueBatch = async () => {
    setBusy(true); setError(null);
    try {
      const result = await batchIssueTrainingCertificates(eligibilitySelected, issueReason);
      setEligibilitySelected(result.items.filter((item) => item.status === "BLOCKED").map((item) => item.record_id));
      await Promise.all([client.invalidateQueries({ queryKey: ["training", "certificates"] }), client.invalidateQueries({ queryKey: ["training", "certificate-eligibility"] })]);
      if (result.blocked) setError(`${result.issued} issued; ${result.blocked} record(s) need attention. Review the blockers below.`);
      else setEligibilityOpen(false);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Batch certificate issuance failed."); } finally { setBusy(false); }
  };

  return <div className="tos-stack training-route-workspace">
    <section className="tos-card tos-route-commandbar"><div><p className="tos-kicker">Controlled evidence</p><h2>Certificate register</h2><p>Issue evidence from completion gates, download controlled artifacts and preserve revoke/supersede/reissue history.</p></div><button disabled={!canIssue} onClick={() => setEligibilityOpen(true)}><ShieldCheck size={16} /> Issue eligible</button><button onClick={onOpenImport}><FileUp size={16} /> Import external evidence</button><button disabled={!canExport || !selected.length} onClick={() => void downloadTrainingCertificateArtifactsBatch(selected)}><Download size={16} /> Download {selected.length || "batch"}</button><button onClick={() => void certificates.refetch()}><RefreshCw size={16} /></button></section>
    {error ? <div className="tos-banner tos-banner--error">{error}<button onClick={() => setError(null)}>×</button></div> : null}
    <section className="tos-card tos-register-card"><div className="tos-register-toolbar"><label className="tos-search-field"><Search size={17} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search person, course or certificate number" /></label><span>{selected.length} selected</span></div>{certificates.isError ? <div className="tos-empty"><strong>Certificate source unavailable</strong><span>The register is Unknown, not empty.</span></div> : !rows.length && !certificates.isLoading ? <div className="tos-empty"><BadgeCheck size={24} /><strong>No matching certificates</strong><span>Issue eligible completions or import governed external evidence.</span></div> : <div className="tos-table-wrap"><table className="tos-table"><thead><tr><th><span className="sr-only">Select</span></th><th>Certificate</th><th>Person</th><th>Course</th><th>Completion / validity</th><th>Status</th><th>Actions</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td><input type="checkbox" checked={selected.includes(row.id)} onChange={(e) => setSelected(e.target.checked ? [...selected, row.id] : selected.filter((id) => id !== row.id))} /></td><td><strong>{row.certificate_reference || "Number pending"}</strong><small>{row.certificate_issued_at ? new Date(row.certificate_issued_at).toLocaleDateString() : "Issue date unavailable"}</small></td><td>{personById.get(row.user_id)?.full_name || row.user_id}<small>{personById.get(row.user_id)?.staff_code}</small></td><td>{row.course_code || row.course?.course_id}<small>{row.course_name || row.course?.course_name}</small></td><td>{row.completion_date}<small>Valid until {row.valid_until || "not limited"}</small></td><td><span className={`tos-pill ${row.certificate_status === "REVOKED" ? "tos-pill--critical" : "tos-pill--ok"}`}>{row.certificate_status || "VALID"}</span></td><td><div className="tos-actions"><button disabled={!canExport} title="Download certificate" onClick={() => void downloadTrainingCertificateArtifact(row.id)}><Download size={15} /></button><button disabled={!canRevoke || row.certificate_status === "REVOKED"} title="Revoke" onClick={() => setLifecycle({ recordId: row.id, action: "REVOKE", reason: "" })}><ShieldX size={15} /></button><button disabled={!canReissue} title="Controlled reissue" onClick={() => setLifecycle({ recordId: row.id, action: "REISSUE", reason: "" })}><RotateCw size={15} /></button></div></td></tr>)}</tbody></table></div>}<footer className="tos-pagination"><span>Page {Math.floor(offset / PAGE_SIZE) + 1}</span><div><button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}><ChevronLeft size={17} /></button><button disabled={!certificates.data?.hasMore} onClick={() => setOffset(offset + PAGE_SIZE)}><ChevronRight size={17} /></button></div></footer></section>
    <Drawer title={lifecycle?.action === "REVOKE" ? "Revoke certificate" : "Reissue certificate"} isOpen={Boolean(lifecycle)} onClose={() => setLifecycle(null)} panelClassName="training-form-drawer training-form-drawer--compact"><div className="tos-drawer-form"><p>This action creates a status-history entry and immediately updates public verification.</p><label>Controlled reason<textarea value={lifecycle?.reason || ""} onChange={(e) => lifecycle && setLifecycle({ ...lifecycle, reason: e.target.value })} /></label><div className="tos-actions"><button onClick={() => setLifecycle(null)}>Cancel</button><button className="primary-chip-btn" disabled={busy || (lifecycle?.reason.trim().length || 0) < 3} onClick={() => void runLifecycle()}>{lifecycle?.action === "REVOKE" ? "Revoke" : "Reissue"}</button></div></div></Drawer>
    <Drawer title="Certificate eligibility" isOpen={eligibilityOpen} onClose={() => setEligibilityOpen(false)} panelClassName="training-form-drawer"><div className="tos-drawer-form"><p>Select only records whose configured attendance, assessment, OJT and evidence gates are satisfied. Blocked rows remain unchanged.</p><label>Search completions<input value={eligibilitySearch} onChange={(e) => setEligibilitySearch(e.target.value)} placeholder="Person, staff code or course" /></label>{eligibility.isLoading ? <div className="tos-empty">Checking completion gates…</div> : eligibility.isError ? <div className="tos-empty"><strong>Eligibility is Unknown</strong><span>Retry before issuing certificates.</span></div> : <div className="tos-list">{(eligibility.data?.items || []).map((item) => <div key={item.record_id}><input type="checkbox" aria-label={`Select ${item.person_name} ${item.course_code}`} disabled={!item.eligible} checked={eligibilitySelected.includes(item.record_id)} onChange={(e) => setEligibilitySelected(e.target.checked ? [...eligibilitySelected, item.record_id] : eligibilitySelected.filter((id) => id !== item.record_id))} /><div><strong>{item.person_name} · {item.course_code}</strong><small>{item.completion_date} · {item.eligible ? "All completion gates satisfied" : item.blockers.map((blocker) => blocker.message).join(" ")}</small></div><span className={`tos-pill ${item.eligible ? "tos-pill--ok" : "tos-pill--critical"}`}>{item.eligible ? "Eligible" : "Blocked"}</span></div>)}</div>}<label>Issuance reason<textarea value={issueReason} onChange={(e) => setIssueReason(e.target.value)} /></label><div className="tos-actions"><button onClick={() => setEligibilityOpen(false)}>Cancel</button><button className="primary-chip-btn" disabled={busy || !eligibilitySelected.length || issueReason.trim().length < 8} onClick={() => void issueBatch()}>Issue {eligibilitySelected.length} certificate(s)</button></div></div></Drawer>
  </div>;
};

export default TrainingCertificatesWorkspace;
