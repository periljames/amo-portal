import { useMemo, useState, type FormEvent } from "react";
import { Send, Users } from "lucide-react";

import {
  createDistributionCampaign,
  issueDistributionCampaign,
  type DocumentDetailResponse,
  type PersonSummary,
} from "../../services/documentControl";
import { DocumentControlEmpty } from "./DocumentControlShell";


type DetailWithPeople = DocumentDetailResponse & { active_users?: PersonSummary[] };
type AudienceMode = "ALL_ELIGIBLE_USERS" | "SELECTED_USERS";

function personLabel(person: PersonSummary): string {
  return `${person.name || person.email} · ${person.role}${person.department ? ` · ${person.department}` : ""}`;
}

export default function DocumentControlDistributionActions({
  detail,
  tenant,
  onChanged,
}: {
  detail: DocumentDetailResponse;
  tenant: string;
  onChanged: () => void;
}) {
  const revision = detail.document.latest_revision;
  const activeUsers = useMemo(
    () => ((detail as DetailWithPeople).active_users || []).filter((person) => person.active),
    [detail],
  );
  const [audienceMode, setAudienceMode] = useState<AudienceMode>("ALL_ELIGIBLE_USERS");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [title, setTitle] = useState(
    revision ? `${detail.document.code} · Rev ${revision.revision_number} controlled distribution` : "",
  );
  const [dueAt, setDueAt] = useState("");
  const [ackRequired, setAckRequired] = useState(detail.document.profile.acknowledgement_required);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const recipientIds = audienceMode === "SELECTED_USERS" ? selectedIds : [];
  const canSubmit = Boolean(
    revision
    && title.trim()
    && activeUsers.length
    && (audienceMode === "ALL_ELIGIBLE_USERS" || selectedIds.length),
  );

  const toggleUser = (id: string) => {
    setSelectedIds((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!revision || !canSubmit) return;
    setBusy(true);
    setError("");
    try {
      const campaign = await createDistributionCampaign(tenant, {
        manual_id: detail.document.id,
        revision_id: revision.id,
        title: title.trim(),
        audience: { mode: audienceMode },
        acknowledgement_required: ackRequired,
        due_at: dueAt ? new Date(dueAt).toISOString() : null,
        recipient_user_ids: recipientIds,
        metadata: { source: "document-control-record" },
      });
      await issueDistributionCampaign(tenant, campaign.id, {
        recipient_user_ids: recipientIds,
        due_at: dueAt ? new Date(dueAt).toISOString() : null,
      });
      onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The controlled distribution could not be issued.");
    } finally {
      setBusy(false);
    }
  };

  if (!revision) {
    return <DocumentControlEmpty title="No revision available" message="Upload a controlled source revision before creating a distribution campaign." />;
  }

  return <form className="dc-form" onSubmit={submit}>
    <div className="dc-callout"><Users size={17} /><div><strong>Controlled digital distribution</strong><div>Issue the revision to all eligible active tenant users or a selected subset. Portal notifications are created automatically.</div></div></div>
    <label className="wide"><span>Campaign title</span><input value={title} onChange={(event) => setTitle(event.target.value)} required /></label>
    <label><span>Audience</span><select value={audienceMode} onChange={(event) => setAudienceMode(event.target.value as AudienceMode)}><option value="ALL_ELIGIBLE_USERS">All eligible active users</option><option value="SELECTED_USERS">Selected active users</option></select></label>
    <label><span>Read-and-acknowledge due</span><input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} /></label>
    <label><span><input type="checkbox" checked={ackRequired} onChange={(event) => setAckRequired(event.target.checked)} disabled={detail.document.profile.acknowledgement_required} /> Acknowledgement required</span><small>{detail.document.profile.acknowledgement_required ? "Required by the document control profile." : "Enable for formal read-and-understand evidence."}</small></label>
    {audienceMode === "SELECTED_USERS" ? <fieldset className="wide dc-recipient-picker"><legend>Select active tenant users</legend>{activeUsers.map((person) => <label key={person.id}><span><input type="checkbox" checked={selectedIds.includes(person.id)} onChange={() => toggleUser(person.id)} /> {personLabel(person)}</span></label>)}</fieldset> : <div className="wide dc-callout"><Users size={16} /><div><strong>{activeUsers.length} active tenant users available</strong><div>The server will exclude system accounts and anyone outside this document’s restricted access scope.</div></div></div>}
    {!activeUsers.length ? <div className="dc-form__error">No active non-system tenant users are available for controlled distribution.</div> : null}
    {error ? <div className="dc-form__error">{error}</div> : null}
    <div className="dc-form__actions"><button type="submit" className="dc-button dc-button--primary" disabled={busy || !canSubmit}><Send size={14} /> {busy ? "Issuing and notifying…" : "Issue and notify recipients"}</button></div>
  </form>;
}
