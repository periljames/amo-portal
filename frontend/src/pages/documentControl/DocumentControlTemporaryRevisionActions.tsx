import { useMemo, useState, type FormEvent } from "react";
import { FileClock, Plus } from "lucide-react";

import {
  createTemporaryRevision,
  transitionTemporaryRevision,
  type DocumentDetailResponse,
} from "../../services/documentControl";
import { DocumentControlEmpty } from "./DocumentControlShell";

const TR_NEXT: Record<string, string[]> = {
  DRAFT: ["IN_REVIEW", "WITHDRAWN"],
  IN_REVIEW: ["DRAFT", "APPROVED", "WITHDRAWN"],
  APPROVED: ["IN_FORCE", "WITHDRAWN"],
  IN_FORCE: ["EXPIRED", "WITHDRAWN", "INCORPORATED"],
  EXPIRED: ["INCORPORATED", "WITHDRAWN"],
};

function statementsFrom(value: string): string[] {
  return value.split(/[\n;]+/).map((item) => item.trim()).filter(Boolean);
}

function revisionLabel(revision: DocumentDetailResponse["revisions"][number]): string {
  return `${revision.issue_number ? `Issue ${revision.issue_number} · ` : ""}Rev ${revision.revision_number} · ${revision.status}`;
}

export default function DocumentControlTemporaryRevisionActions({
  detail,
  tenant,
  onChanged,
}: {
  detail: DocumentDetailResponse;
  tenant: string;
  onChanged: () => void;
}) {
  const publishedRevisionId = detail.document.current_published_revision_id;
  const latest = detail.document.latest_revision;
  const sourceRevisionId = latest && latest.id !== publishedRevisionId && !latest.immutable ? latest.id : "";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [number, setNumber] = useState("");
  const [title, setTitle] = useState("");
  const [reason, setReason] = useState("");
  const [affectedSections, setAffectedSections] = useState("");
  const [filingInstructions, setFilingInstructions] = useState("");
  const [effective, setEffective] = useState("");
  const [expiry, setExpiry] = useState("");
  const [selectedId, setSelectedId] = useState(detail.temporary_revisions[0]?.id || "");
  const selected = detail.temporary_revisions.find((row) => row.id === selectedId) || detail.temporary_revisions[0];
  const nextStates = selected ? TR_NEXT[selected.status] || [] : [];
  const [nextStatus, setNextStatus] = useState(nextStates[0] || "IN_REVIEW");
  const [campaignId, setCampaignId] = useState("");
  const [incorporatedRevisionId, setIncorporatedRevisionId] = useState("");

  const eligibleCampaigns = useMemo(() => {
    if (!selected) return [];
    const expectedRevisionId = selected.revision_id || selected.base_revision_id;
    return detail.distribution_campaigns.filter((campaign) =>
      campaign.temporary_revision_id === selected.id
      && campaign.revision_id === expectedRevisionId
      && ["ISSUED", "COMPLETED"].includes(campaign.status),
    );
  }, [detail.distribution_campaigns, selected]);

  const eligibleIncorporatingRevisions = useMemo(() => {
    if (!selected) return [];
    return detail.revisions.filter((revision) =>
      ["PUBLISHED", "SUPERSEDED"].includes(revision.status)
      && revision.id !== selected.base_revision_id
      && revision.id !== selected.revision_id,
    );
  }, [detail.revisions, selected]);

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await action();
      onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The temporary revision action failed.");
    } finally {
      setBusy(false);
    }
  };

  const create = (event: FormEvent) => {
    event.preventDefault();
    if (!publishedRevisionId || !sourceRevisionId) return;
    void run(() => createTemporaryRevision(tenant, {
      manual_id: detail.document.id,
      base_revision_id: publishedRevisionId,
      revision_id: sourceRevisionId,
      tr_number: number,
      title,
      reason,
      affected_sections: statementsFrom(affectedSections).map((section) => ({ section })),
      filing_instructions: filingInstructions,
      effective_date: effective,
      expiry_date: expiry,
    }));
  };

  const selectTemporaryRevision = (id: string) => {
    setSelectedId(id);
    const row = detail.temporary_revisions.find((item) => item.id === id);
    setNextStatus(row ? (TR_NEXT[row.status] || [])[0] || "" : "");
    setCampaignId("");
    setIncorporatedRevisionId("");
    setError("");
  };

  const transition = () => {
    if (!selected || !nextStatus) return;
    if (nextStatus === "IN_FORCE" && !campaignId) {
      setError("Select the issued distribution campaign for this temporary revision before placing it in force.");
      return;
    }
    if (nextStatus === "INCORPORATED" && !incorporatedRevisionId) {
      setError("Select the published permanent revision that incorporates this temporary revision.");
      return;
    }
    void run(() => transitionTemporaryRevision(tenant, selected.id, {
      status: nextStatus,
      approval_status: nextStatus === "APPROVED" ? "APPROVED" : undefined,
      distribution_campaign_id: nextStatus === "IN_FORCE" ? campaignId : null,
      incorporated_revision_id: nextStatus === "INCORPORATED" ? incorporatedRevisionId : null,
    }));
  };

  const sourceError = !publishedRevisionId
    ? "A published revision is required before creating a temporary revision."
    : !sourceRevisionId
      ? "Upload an uncontrolled source revision containing the temporary amendment before creating the TR record."
      : "";

  return <div className="dc-grid">
    <form className="dc-form" onSubmit={create}>
      <div className="dc-callout"><FileClock size={17} /><div><strong>Temporary revision source required</strong><div>The temporary amendment must exist as a separate uncontrolled revision before its TR control record can be created.</div></div></div>
      <label><span>TR number</span><input value={number} onChange={(event) => setNumber(event.target.value)} required /></label>
      <label><span>Effective date</span><input type="date" value={effective} onChange={(event) => setEffective(event.target.value)} required /></label>
      <label className="wide"><span>Subject</span><input value={title} onChange={(event) => setTitle(event.target.value)} required /></label>
      <label className="wide"><span>Reason</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} required /></label>
      <label className="wide"><span>Affected sections or insertion points</span><textarea value={affectedSections} onChange={(event) => setAffectedSections(event.target.value)} placeholder="One section or insertion point per line" required /></label>
      <label className="wide"><span>Filing instructions</span><textarea value={filingInstructions} onChange={(event) => setFilingInstructions(event.target.value)} placeholder="State where and how the temporary revision must be filed and removed" required /></label>
      <label><span>Expiry or incorporation due</span><input type="date" value={expiry} onChange={(event) => setExpiry(event.target.value)} required /></label>
      {error || sourceError ? <div className="dc-form__error">{error || sourceError}</div> : null}
      <div className="dc-form__actions"><button type="submit" className="dc-button" disabled={busy || Boolean(sourceError)}><Plus size={14} /> Create temporary revision</button></div>
    </form>

    {selected ? <div className="dc-form">
      <label className="wide"><span>Temporary revision</span><select value={selected.id} onChange={(event) => selectTemporaryRevision(event.target.value)}>{detail.temporary_revisions.map((row) => <option key={row.id} value={row.id}>{row.tr_number} · {row.status} · expires {row.expiry_date}</option>)}</select></label>
      <label><span>Next status</span><select value={nextStatus} onChange={(event) => { setNextStatus(event.target.value); setCampaignId(""); setIncorporatedRevisionId(""); setError(""); }}>{nextStates.map((status) => <option key={status}>{status}</option>)}</select></label>

      {nextStatus === "IN_FORCE" ? <label className="wide"><span>Issued TR distribution</span><select value={campaignId} onChange={(event) => setCampaignId(event.target.value)} required><option value="">Select issued campaign</option>{eligibleCampaigns.map((campaign) => <option key={campaign.id} value={campaign.id}>{campaign.title} · {campaign.status}</option>)}</select><small>{eligibleCampaigns.length ? "Only campaigns issued for this TR source are available." : "Issue a distribution campaign for this temporary revision before effectivity."}</small></label> : null}

      {nextStatus === "INCORPORATED" ? <label className="wide"><span>Incorporating permanent revision</span><select value={incorporatedRevisionId} onChange={(event) => setIncorporatedRevisionId(event.target.value)} required><option value="">Select published permanent revision</option>{eligibleIncorporatingRevisions.map((revision) => <option key={revision.id} value={revision.id}>{revisionLabel(revision)}</option>)}</select><small>{eligibleIncorporatingRevisions.length ? "The selected permanent revision will be retained as the incorporation evidence link." : "Publish the permanent incorporating revision before closing this TR as incorporated."}</small></label> : null}

      {error ? <div className="dc-form__error">{error}</div> : null}
      <div className="dc-form__actions"><button type="button" className="dc-button dc-button--primary" disabled={busy || !nextStatus || (nextStatus === "IN_FORCE" && !campaignId) || (nextStatus === "INCORPORATED" && !incorporatedRevisionId)} onClick={transition}><FileClock size={14} /> Apply temporary revision transition</button></div>
    </div> : <DocumentControlEmpty title="No temporary revision" message="Upload temporary amendment content, then create its controlled TR record." />}
  </div>;
}
