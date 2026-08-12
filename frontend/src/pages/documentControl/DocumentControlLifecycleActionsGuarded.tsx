import { useMemo, useState, type FormEvent } from "react";
import { Archive, Copy } from "lucide-react";

import {
  createControlledCopy,
  createControlledCopyEvent,
  type DocumentDetailResponse,
  type PersonSummary,
} from "../../services/documentControl";
import type { DocumentEvidenceReference } from "../../services/documentControlEvidence";
import DocumentControlApproverLifecycleActions from "./DocumentControlApproverLifecycleActions";
import DocumentControlControllerLifecycleActions from "./DocumentControlControllerLifecycleActions";
import DocumentControlReviewActions from "./DocumentControlReviewActions";
import DocumentControlReviewerLifecycleActions from "./DocumentControlReviewerLifecycleActions";
import DocumentControlTemporaryRevisionActions from "./DocumentControlTemporaryRevisionActions";
import DocumentEvidencePicker from "./DocumentEvidencePicker";
import { DocumentControlEmpty } from "./DocumentControlShell";


export type LifecycleView = "workflow" | "authority" | "temporary-revisions" | "copies" | "reviews";

type Props = {
  detail: DocumentDetailResponse;
  tenant: string;
  activeView: LifecycleView;
  onChanged: () => void;
};

type DetailWithPeople = DocumentDetailResponse & {
  active_users?: PersonSummary[];
  capabilities: DocumentDetailResponse["capabilities"] & { approve?: boolean; review?: boolean };
};

const COPY_EVENTS: Record<string, string[]> = {
  ISSUED: ["TRANSFER", "LOCATION_CHANGE", "RECALL", "RETURN", "WITHDRAW", "DESTROY"],
  RECALLED: ["RETURN", "WITHDRAW", "DESTROY"],
  RETURNED: ["WITHDRAW", "DESTROY"],
  WITHDRAWN: ["DESTROY"],
};

const DECISION_SEPARATED_VIEWS = new Set<LifecycleView>([
  "workflow",
  "authority",
  "temporary-revisions",
]);

function ErrorMessage({ message }: { message: string }) {
  return message ? <div className="dc-form__error">{message}</div> : null;
}

function personLabel(person: PersonSummary): string {
  return `${person.name || person.email} · ${person.role}${person.department ? ` · ${person.department}` : ""}`;
}

function ControlledCopyCanonicalActions({ detail, tenant, onChanged }: Omit<Props, "activeView">) {
  const published = detail.revisions.find((revision) => revision.status === "PUBLISHED");
  const activeUsers = useMemo(
    () => ((detail as DetailWithPeople).active_users || []).filter((person) => person.active),
    [detail],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copyNumber, setCopyNumber] = useState("");
  const [location, setLocation] = useState("");
  const [holderUserId, setHolderUserId] = useState("");
  const [selectedId, setSelectedId] = useState(detail.controlled_copies[0]?.id || "");
  const selected = detail.controlled_copies.find((row) => row.id === selectedId) || detail.controlled_copies[0];
  const events = selected ? COPY_EVENTS[selected.status] || [] : [];
  const [eventType, setEventType] = useState(events[0] || "");
  const [toHolderUserId, setToHolderUserId] = useState("");
  const [toLocation, setToLocation] = useState("");
  const [reason, setReason] = useState("");
  const [evidence, setEvidence] = useState<DocumentEvidenceReference[]>([]);

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await action();
      onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The controlled-copy action failed.");
    } finally {
      setBusy(false);
    }
  };

  const create = (event: FormEvent) => {
    event.preventDefault();
    if (!published || !holderUserId) return;
    void run(() => createControlledCopy(tenant, {
      manual_id: detail.document.id,
      revision_id: published.id,
      copy_number: copyNumber,
      format: "HARDCOPY",
      holder_user_id: holderUserId,
      holder_name: null,
      location_text: location,
      metadata: {},
    }));
  };

  const selectCopy = (id: string) => {
    setSelectedId(id);
    const row = detail.controlled_copies.find((item) => item.id === id);
    setEventType(row ? (COPY_EVENTS[row.status] || [])[0] || "" : "");
    setToHolderUserId("");
    setToLocation("");
    setReason("");
    setEvidence([]);
  };

  const addEvent = () => {
    if (!selected || !eventType) return;
    if (eventType === "TRANSFER" && !toHolderUserId) {
      setError("Select the active tenant user receiving this controlled copy.");
      return;
    }
    if (["TRANSFER", "LOCATION_CHANGE"].includes(eventType) && !toLocation.trim()) {
      setError("Record the new controlled location for this custody event.");
      return;
    }
    if (["WITHDRAW", "DESTROY"].includes(eventType) && !evidence.length) {
      setError(`${eventType === "DESTROY" ? "Destruction" : "Withdrawal"} evidence must be retained before this custody event can be recorded.`);
      return;
    }
    void run(() => createControlledCopyEvent(tenant, selected.id, {
      event_type: eventType,
      to_holder_user_id: toHolderUserId || null,
      to_location: toLocation.trim() || null,
      reason: reason.trim() || null,
      evidence,
    }));
  };

  const userDirectoryError = activeUsers.length
    ? ""
    : "No active, non-system tenant users are available for controlled-copy custody.";

  return <div className="dc-grid">
    <form className="dc-form" onSubmit={create}>
      <label><span>Copy number</span><input value={copyNumber} onChange={(event) => setCopyNumber(event.target.value)} required /></label>
      <label><span>Canonical holder</span><select value={holderUserId} onChange={(event) => setHolderUserId(event.target.value)} required><option value="">Select active tenant user</option>{activeUsers.map((person) => <option key={person.id} value={person.id}>{personLabel(person)}</option>)}</select></label>
      <label className="wide"><span>Physical controlled location</span><input value={location} onChange={(event) => setLocation(event.target.value)} required /></label>
      <ErrorMessage message={error || userDirectoryError || (!published ? "A published revision is required before issuing a controlled copy." : "")} />
      <div className="dc-form__actions"><button type="submit" className="dc-button" disabled={busy || !published || !holderUserId || !activeUsers.length}><Copy size={14} /> Issue controlled copy</button></div>
    </form>
    {selected ? <div className="dc-form">
      <label className="wide"><span>Controlled copy</span><select value={selected.id} onChange={(event) => selectCopy(event.target.value)}>{detail.controlled_copies.map((row) => <option key={row.id} value={row.id}>{row.copy_number} · {row.status} · {row.location_text}</option>)}</select></label>
      <label><span>Custody event</span><select value={eventType} onChange={(event) => setEventType(event.target.value)}>{events.map((value) => <option key={value}>{value}</option>)}</select></label>
      <label><span>Receiving active tenant user</span><select value={toHolderUserId} onChange={(event) => setToHolderUserId(event.target.value)}><option value="">No holder change</option>{activeUsers.map((person) => <option key={person.id} value={person.id}>{personLabel(person)}</option>)}</select></label>
      <label><span>New controlled location</span><input value={toLocation} onChange={(event) => setToLocation(event.target.value)} /></label>
      <label className="wide"><span>Reason</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label>
      <DocumentEvidencePicker
        tenant={tenant}
        manualId={detail.document.id}
        revisionId={selected.revision_id}
        category="CONTROLLED_COPY"
        purpose={eventType ? `CONTROLLED_COPY_${eventType}` : "CONTROLLED_COPY_EVENT"}
        value={evidence}
        onChange={setEvidence}
        label="Custody / disposition evidence"
        help="Attach transfer, return, withdrawal or destruction evidence. Destruction and withdrawal require at least one retained file."
      />
      <ErrorMessage message={error || userDirectoryError} />
      <div className="dc-form__actions"><button type="button" className="dc-button dc-button--primary" disabled={busy || !eventType || !activeUsers.length} onClick={addEvent}><Archive size={14} /> Record custody event</button></div>
    </div> : <DocumentControlEmpty title="No numbered copy" message="Issue a copy only from the effective published revision and assign it to an active tenant user." />}
  </div>;
}

export default function DocumentControlLifecycleActionsGuarded(props: Props) {
  const capabilities = (props.detail as DetailWithPeople).capabilities;
  const canApprove = Boolean(capabilities?.approve);
  const canControl = Boolean(capabilities?.control);
  const canReview = Boolean(capabilities?.review);

  if (canReview && !canControl) {
    if (props.activeView === "workflow") {
      return <DocumentControlReviewerLifecycleActions detail={props.detail} tenant={props.tenant} onChanged={props.onChanged} />;
    }
    return <DocumentControlEmpty title="No reviewer action" message="This assigned reviewer account may act only on its current document workflow decision." />;
  }

  if (props.activeView === "copies") {
    return <ControlledCopyCanonicalActions detail={props.detail} tenant={props.tenant} onChanged={props.onChanged} />;
  }
  if (props.activeView === "reviews") {
    return <DocumentControlReviewActions detail={props.detail} tenant={props.tenant} onChanged={props.onChanged} />;
  }
  if (props.activeView === "temporary-revisions" && canApprove) {
    return <DocumentControlTemporaryRevisionActions detail={props.detail} tenant={props.tenant} onChanged={props.onChanged} />;
  }
  if (canApprove && (props.activeView === "workflow" || props.activeView === "authority")) {
    return <DocumentControlApproverLifecycleActions {...props} />;
  }
  if (!canApprove && DECISION_SEPARATED_VIEWS.has(props.activeView)) {
    return <DocumentControlControllerLifecycleActions {...props} />;
  }
  return <DocumentControlEmpty title="No governed action" message="This lifecycle view has no active production action for the current role. Legacy raw-ID forms are intentionally not reachable." />;
}
