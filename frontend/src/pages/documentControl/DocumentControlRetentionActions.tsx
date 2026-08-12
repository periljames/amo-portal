import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Archive, Ban, CheckCircle2, FileCheck2, LockKeyhole, RefreshCw, ShieldAlert, Trash2 } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import type { DocumentDetailResponse } from "../../services/documentControl";
import {
  uploadDocumentEvidenceAsset,
  type DocumentEvidenceAsset,
} from "../../services/documentControlEvidence";
import { getDocumentControlAdministration } from "../../services/documentControlReports";
import {
  createDocumentRetention,
  decideDocumentDisposition,
  getDocumentRetentionSources,
  listDocumentRetention,
  listDocumentRetentionApprovers,
  recordDocumentDisposition,
  requestDocumentDisposition,
  updateDocumentRetentionHold,
  type DocumentRetentionApprover,
  type DocumentRetentionRecord,
  type DocumentRetentionSourceCatalogue,
  type DocumentRetentionSourceType,
} from "../../services/documentControlRetention";


type Props = { tenant: string; detail: DocumentDetailResponse; onChanged: () => void };
type RetentionCapabilities = DocumentDetailResponse["capabilities"] & { approve?: boolean };

function dateText(value?: string | null): string {
  if (!value) return "No disposal date set";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString();
}

export default function DocumentControlRetentionActions({ tenant, detail, onChanged }: Props) {
  const [params] = useSearchParams();
  const retentionFocusId = params.get("retention") || "";
  const canApprove = Boolean((detail.capabilities as RetentionCapabilities).approve);
  const [items, setItems] = useState<DocumentRetentionRecord[]>([]);
  const [sources, setSources] = useState<DocumentRetentionSourceCatalogue | null>(null);
  const [approvers, setApprovers] = useState<DocumentRetentionApprover[]>([]);
  const [classes, setClasses] = useState<string[]>(["STANDARD", "PERMANENT"]);
  const [sourceType, setSourceType] = useState<DocumentRetentionSourceType>("DOCUMENT");
  const [sourceId, setSourceId] = useState("");
  const [retentionClass, setRetentionClass] = useState("STANDARD");
  const [retentionUntil, setRetentionUntil] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [approverId, setApproverId] = useState("");
  const [reason, setReason] = useState("");
  const [method, setMethod] = useState("CONTROLLED_DESTRUCTION");
  const [certificate, setCertificate] = useState<DocumentEvidenceAsset | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [retention, sourceCatalogue, availableApprovers, admin] = await Promise.all([
        listDocumentRetention(tenant, detail.document.id),
        getDocumentRetentionSources(tenant, detail.document.id),
        listDocumentRetentionApprovers(tenant),
        getDocumentControlAdministration(tenant).catch(() => null),
      ]);
      setItems(retention);
      setSources(sourceCatalogue);
      if (retentionFocusId && retention.some((item) => item.id === retentionFocusId)) {
        setSelectedId(retentionFocusId);
      }
      setApprovers(availableApprovers);
      setApproverId((current) => current && availableApprovers.some((item) => item.id === current)
        ? current
        : availableApprovers[0]?.id || "");
      const configured = (admin?.retention_classes || [])
        .map((item) => String(item.code || "").trim().toUpperCase())
        .filter(Boolean);
      if (configured.length) {
        setClasses(configured);
        if (!configured.includes(retentionClass)) setRetentionClass(configured[0]);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Retention controls could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [detail.document.id, retentionClass, retentionFocusId, tenant]);

  useEffect(() => { void load(); }, [load]);

  const selected = useMemo(() => items.find((item) => item.id === selectedId) || null, [items, selectedId]);
  const sourceOptions = useMemo(() => {
    if (!sources) return [];
    if (sourceType === "REVISION") return sources.revisions;
    if (sourceType === "EVIDENCE_ASSET") return sources.evidence_assets;
    if (sourceType === "GENERATED_RECORD") return sources.generated_records;
    return [];
  }, [sourceType, sources]);

  const create = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await createDocumentRetention(tenant, {
        manual_id: detail.document.id,
        source_type: sourceType,
        source_id: sourceType === "DOCUMENT" ? null : sourceId,
        retention_class: retentionClass,
        retention_until: retentionUntil ? new Date(`${retentionUntil}T23:59:59`).toISOString() : null,
      });
      setSourceType("DOCUMENT");
      setSourceId("");
      setRetentionUntil("");
      await load();
      onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Retention record could not be created.");
    } finally {
      setBusy(false);
    }
  };

  const act = async (operation: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await operation();
      setReason("");
      await load();
      onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Retention action could not be completed.");
    } finally {
      setBusy(false);
    }
  };

  const uploadCertificate = async (file: File | null) => {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const asset = await uploadDocumentEvidenceAsset(tenant, detail.document.id, {
        file,
        revisionId: selected?.revision_id || detail.document.latest_revision?.id || null,
        category: "GENERAL",
        purpose: "DISPOSITION_CERTIFICATE",
        description: selected ? `Disposition certificate for ${selected.source_label}` : "Disposition certificate",
      });
      setCertificate(asset);
      setSources((current) => current ? {
        ...current,
        evidence_assets: [
          { id: asset.asset_id, label: asset.filename, status: asset.category, revision_id: asset.revision_id, sha256: asset.sha256 },
          ...current.evidence_assets.filter((item) => item.id !== asset.asset_id),
        ],
      } : current);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Disposition certificate could not be retained.");
    } finally {
      setBusy(false);
    }
  };

  return <div className="dc-form" data-testid="document-control-retention-actions">
    <div className="dc-callout"><Archive size={17} /><div><strong>Retain → approve disposition → prove</strong><div>Retention and disposition are controlled states. Recording disposition never hard-deletes the controlled history or audit evidence that proves what was approved.</div></div></div>

    <form className="dc-grid" onSubmit={create}>
      <label><span>Governed source</span><select value={sourceType} onChange={(event) => { setSourceType(event.target.value as DocumentRetentionSourceType); setSourceId(""); }}><option value="DOCUMENT">Whole controlled document</option><option value="REVISION">Specific revision</option><option value="EVIDENCE_ASSET">Retained evidence asset</option>{sources?.generated_records.length ? <option value="GENERATED_RECORD">Generated controlled record</option> : null}</select></label>
      {sourceType !== "DOCUMENT" ? <label><span>Source record</span><select required value={sourceId} onChange={(event) => setSourceId(event.target.value)}><option value="">Select controlled source</option>{sourceOptions.map((item) => <option key={item.id} value={item.id}>{item.label}{item.status ? ` · ${item.status.replaceAll("_", " ")}` : ""}</option>)}</select><small>Only records returned by the tenant-scoped server catalogue can be selected.</small></label> : null}
      <label><span>Retention class</span><select value={retentionClass} onChange={(event) => setRetentionClass(event.target.value)}>{classes.map((item) => <option key={item}>{item}</option>)}</select></label>
      <label><span>Retain until</span><input type="date" value={retentionUntil} onChange={(event) => setRetentionUntil(event.target.value)} /></label>
      <div className="dc-form__actions"><button className="dc-button dc-button--primary" type="submit" disabled={busy || (sourceType !== "DOCUMENT" && !sourceId)}><FileCheck2 size={14} /> Govern retention</button></div>
    </form>

    <div className="dc-form__actions"><button type="button" className="dc-button" disabled={loading || busy} onClick={() => void load()}><RefreshCw size={14} /> Refresh retention</button></div>
    {error ? <div className="dc-form__error" role="alert">{error}</div> : null}

    {items.length ? <div className="dc-table-wrap"><table className="dc-table"><thead><tr><th>Controlled source</th><th>Retention</th><th>Status</th><th>Governance</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><strong>{item.source_label}</strong><small>{item.source_type.replaceAll("_", " ")}</small></td><td><strong>{item.retention_class}</strong><small>{dateText(item.retention_until)}</small></td><td><strong>{item.status.replaceAll("_", " ")}</strong>{item.legal_hold ? <small>Legal hold · {item.hold_reason || "Reason retained"}</small> : item.approver_user_id ? <small>Assigned approval retained</small> : null}</td><td><button type="button" className={`dc-button ${selectedId === item.id ? "dc-button--primary" : ""}`} onClick={() => { setSelectedId(item.id); setCertificate(null); setReason(""); }}>Manage</button></td></tr>)}</tbody></table></div> : !loading ? <div className="dc-callout"><CheckCircle2 size={16} /><div><strong>No governed retention records yet</strong><div>Create one for the document, a revision, retained evidence asset or governed generated record when a retention period must be controlled.</div></div></div> : null}

    {selected ? <section className="dc-form wide" aria-label="Selected retention governance">
      <div className="dc-callout"><ShieldAlert size={16} /><div><strong>{selected.source_label}</strong><div>{selected.status.replaceAll("_", " ")} · {selected.retention_class} · {dateText(selected.retention_until)}</div></div></div>
      <label><span>Governance reason / decision justification</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Reason for legal hold, disposition request or decision" /></label>
      {["ACTIVE", "DUE", "REJECTED"].includes(selected.status) && !selected.legal_hold ? <label><span>Assigned disposition approver</span><select value={approverId} onChange={(event) => setApproverId(event.target.value)}><option value="">Select authorized approver</option>{approvers.map((item) => <option key={item.id} value={item.id}>{item.label} · {item.role.replaceAll("_", " ")}</option>)}</select><small>The requester is excluded. Only active users who pass the server&apos;s Document Control approval policy are listed.</small></label> : null}
      <div className="dc-form__actions">
        {canApprove && !selected.legal_hold && selected.status !== "DISPOSED" ? <button type="button" className="dc-button" disabled={busy || !reason.trim()} onClick={() => void act(() => updateDocumentRetentionHold(tenant, selected.id, true, reason))}><LockKeyhole size={14} /> Place legal hold</button> : null}
        {canApprove && selected.legal_hold ? <button type="button" className="dc-button" disabled={busy} onClick={() => void act(() => updateDocumentRetentionHold(tenant, selected.id, false, reason))}><Ban size={14} /> Release legal hold</button> : null}
        {["ACTIVE", "DUE", "REJECTED"].includes(selected.status) && !selected.legal_hold ? <button type="button" className="dc-button" disabled={busy || !reason.trim() || !approverId} onClick={() => void act(() => requestDocumentDisposition(tenant, selected.id, approverId, reason))}><Trash2 size={14} /> Request disposition</button> : null}
        {canApprove && selected.status === "DISPOSITION_REQUESTED" ? <><button type="button" className="dc-button dc-button--primary" disabled={busy || !reason.trim()} onClick={() => void act(() => decideDocumentDisposition(tenant, selected.id, "APPROVE", reason))}><CheckCircle2 size={14} /> Approve disposition</button><button type="button" className="dc-button" disabled={busy || !reason.trim()} onClick={() => void act(() => decideDocumentDisposition(tenant, selected.id, "REJECT", reason))}><Ban size={14} /> Reject</button></> : null}
      </div>
      {selected.status === "DISPOSITION_REQUESTED" && !canApprove ? <div className="dc-form__hint">This disposition is waiting for its named authorized approver. The requester cannot self-approve.</div> : null}
      {selected.status === "APPROVED" ? <div className="dc-grid">
        <label><span>Disposition method</span><select value={method} onChange={(event) => setMethod(event.target.value)}><option value="CONTROLLED_DESTRUCTION">Controlled destruction</option><option value="SECURE_DIGITAL_PURGE">Secure digital purge</option><option value="RETURN_TO_ISSUER">Return to issuer</option><option value="TRANSFER_TO_ARCHIVE">Transfer to archive</option><option value="OTHER">Other documented method</option></select></label>
        <label><span>Disposition certificate evidence</span><input type="file" accept=".pdf,.png,.jpg,.jpeg,.docx,.eml" onChange={(event) => void uploadCertificate(event.target.files?.[0] || null)} /><small>{certificate ? `${certificate.filename} · SHA-256 ${certificate.sha256}` : "Retain the destruction/transfer certificate before recording disposition."}</small></label>
        <div className="dc-form__actions"><button type="button" className="dc-button dc-button--primary" disabled={busy || !certificate} onClick={() => void act(() => recordDocumentDisposition(tenant, selected.id, { disposition_method: method, certificate_evidence_asset_id: certificate!.asset_id, notes: reason }))}><FileCheck2 size={14} /> Record disposition with evidence</button></div>
      </div> : null}
      {selected.status === "DISPOSED" ? <div className="dc-callout dc-callout--success"><CheckCircle2 size={16} /><div><strong>Disposition recorded</strong><div>{selected.disposition_method?.replaceAll("_", " ") || "Controlled method"} · certificate evidence {selected.certificate_evidence_asset_id || "retained"}. Controlled history remains in the audit trail.</div></div></div> : null}
    </section> : null}
  </div>;
}