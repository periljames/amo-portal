import { useMemo, useState, type FormEvent } from "react";
import { FilePlus2, Play, Plus, Save, Send, Settings2, X } from "lucide-react";

import {
  createApplicabilityRule,
  createAuthoritySubmission,
  createControlledCopy,
  createDistributionCampaign,
  createDocumentChangeRequest,
  createDocumentReview,
  createDocumentWorkflow,
  createExternalSource,
  createIntegrationLink,
  createTemporaryRevision,
  issueDistributionCampaign,
  transitionDocumentWorkflow,
  type DocumentDetailResponse,
  type DocumentWorkflow,
} from "../../services/documentControl";
import {
  updateDocumentMetadata,
} from "../../services/documentControlReports";
import { upsertDocumentProfile } from "../../services/documentControl";
import { DocumentControlSection, useDocumentControlRoute } from "./DocumentControlShell";

const WORKFLOW_ACTIONS: Record<string, Array<{ action: string; label: string; danger?: boolean }>> = {
  DRAFT: [{ action: "SUBMIT_TECHNICAL_REVIEW", label: "Submit technical review" }],
  TECHNICAL_REVIEW: [
    { action: "APPROVE_TECHNICAL", label: "Approve technical review" },
    { action: "REQUEST_CORRECTIONS", label: "Request corrections", danger: true },
  ],
  CORRECTIONS_REQUIRED: [{ action: "RESUBMIT_TECHNICAL_REVIEW", label: "Resubmit technical review" }],
  TECHNICAL_APPROVED: [{ action: "START_QUALITY_REVIEW", label: "Start Quality review" }],
  QUALITY_REVIEW: [
    { action: "APPROVE_QUALITY", label: "Approve Quality review" },
    { action: "REQUEST_CORRECTIONS", label: "Request corrections", danger: true },
  ],
  QUALITY_APPROVED: [{ action: "SUBMIT_ACCOUNTABLE_MANAGER", label: "Submit to Accountable Executive" }],
  ACCOUNTABLE_MANAGER_APPROVAL: [
    { action: "APPROVE_ACCOUNTABLE_MANAGER", label: "Approve and schedule" },
    { action: "MARK_AUTHORITY_SUBMITTED", label: "Mark authority submitted" },
    { action: "REQUEST_CORRECTIONS", label: "Request corrections", danger: true },
  ],
  AUTHORITY_SUBMITTED: [
    { action: "MARK_AUTHORITY_APPROVED", label: "Record authority approval" },
    { action: "REQUEST_CORRECTIONS", label: "Return for corrections", danger: true },
  ],
  AUTHORITY_APPROVED: [{ action: "SCHEDULE_EFFECTIVITY", label: "Schedule effectivity" }],
  SCHEDULED_FOR_EFFECTIVITY: [
    { action: "PUBLISH", label: "Publish revision" },
    { action: "REQUEST_CORRECTIONS", label: "Return for corrections", danger: true },
  ],
  PUBLISHED: [{ action: "ARCHIVE", label: "Archive revision", danger: true }],
};

type ActiveView =
  | "overview"
  | "revisions"
  | "changes"
  | "workflow"
  | "authority"
  | "temporary-revisions"
  | "distribution"
  | "compliance"
  | "applicability"
  | "copies"
  | "reviews"
  | "integrations"
  | "external"
  | "history";

export default function DocumentControlRecordActions({
  detail,
  onChanged,
  compact = false,
  activeView = "overview",
}: {
  detail: DocumentDetailResponse;
  onChanged: () => void;
  compact?: boolean;
  activeView?: ActiveView;
}) {
  const [open, setOpen] = useState(!compact);
  const { tenant } = useDocumentControlRoute();
  if (compact) {
    return <button type="button" className="dc-button" onClick={() => setOpen((value) => !value)}><Settings2 size={14} /> Manage</button>;
  }
  if (!open) return null;
  const title = activeView === "overview" || activeView === "history" || activeView === "revisions" || activeView === "compliance"
    ? "Document controls"
    : `Create or update ${activeView.replaceAll("-", " ")}`;
  return (
    <DocumentControlSection title={title} description="All actions write tenant-scoped database records and append an audit event." actions={<button type="button" className="dc-button" onClick={() => setOpen(false)}><X size={14} /> Hide</button>}>
      {activeView === "overview" || activeView === "history" || activeView === "revisions" || activeView === "compliance" ? <ProfileAndMetadataForm detail={detail} tenant={tenant} onChanged={onChanged} /> : null}
      {activeView === "changes" ? <ChangeRequestForm detail={detail} tenant={tenant} onChanged={onChanged} /> : null}
      {activeView === "workflow" ? <WorkflowControls detail={detail} tenant={tenant} onChanged={onChanged} /> : null}
      {activeView === "authority" ? <AuthorityForm detail={detail} tenant={tenant} onChanged={onChanged} /> : null}
      {activeView === "temporary-revisions" ? <TemporaryRevisionForm detail={detail} tenant={tenant} onChanged={onChanged} /> : null}
      {activeView === "distribution" ? <DistributionForm detail={detail} tenant={tenant} onChanged={onChanged} /> : null}
      {activeView === "applicability" ? <ApplicabilityForm detail={detail} tenant={tenant} onChanged={onChanged} /> : null}
      {activeView === "copies" ? <ControlledCopyForm detail={detail} tenant={tenant} onChanged={onChanged} /> : null}
      {activeView === "reviews" ? <ReviewForm detail={detail} tenant={tenant} onChanged={onChanged} /> : null}
      {activeView === "integrations" ? <IntegrationForm detail={detail} tenant={tenant} onChanged={onChanged} /> : null}
      {activeView === "external" ? <ExternalSourceForm detail={detail} tenant={tenant} onChanged={onChanged} /> : null}
    </DocumentControlSection>
  );
}

function useMutation(onChanged: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await action();
      onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The controlled action failed.");
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run };
}

function FormError({ message }: { message: string }) {
  return message ? <div className="dc-form__error">{message}</div> : null;
}

function ProfileAndMetadataForm({ detail, tenant, onChanged }: { detail: DocumentDetailResponse; tenant: string; onChanged: () => void }) {
  const { document } = detail;
  const [title, setTitle] = useState(document.title);
  const [code, setCode] = useState(document.code);
  const [manualType, setManualType] = useState(document.manual_type);
  const [ownerRole, setOwnerRole] = useState(document.owner_role);
  const [documentClass, setDocumentClass] = useState(document.profile.document_class);
  const [ownerDepartment, setOwnerDepartment] = useState(document.profile.owner_department);
  const [language, setLanguage] = useState(document.profile.language);
  const [criticality, setCriticality] = useState(document.profile.criticality);
  const [reviewInterval, setReviewInterval] = useState(String(document.profile.review_interval_months));
  const [nextReview, setNextReview] = useState(document.profile.next_review_due || "");
  const [regulated, setRegulated] = useState(document.profile.regulated_flag);
  const [restricted, setRestricted] = useState(document.profile.restricted_flag);
  const [authority, setAuthority] = useState(document.profile.requires_authority_approval);
  const [ackRequired, setAckRequired] = useState(document.profile.acknowledgement_required);
  const mutation = useMutation(onChanged);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void mutation.run(async () => {
      await updateDocumentMetadata(tenant, document.id, { title, code, manual_type: manualType, owner_role: ownerRole });
      await upsertDocumentProfile(tenant, document.id, {
        document_class: documentClass,
        owner_department: ownerDepartment,
        owner_user_id: document.profile.owner_user_id,
        language,
        criticality,
        regulated_flag: regulated,
        restricted_flag: restricted,
        requires_authority_approval: authority,
        acknowledgement_required: ackRequired,
        review_interval_months: Number(reviewInterval),
        next_review_due: nextReview || null,
        access_scope: document.profile.access_scope,
        tags: document.profile.tags,
        metadata: document.profile.metadata,
        expected_version: document.profile.version || undefined,
      });
    });
  };
  return <form className="dc-form" onSubmit={submit}>
    <label><span>Document code</span><input value={code} onChange={(event) => setCode(event.target.value)} required /></label>
    <label><span>Document class</span><select value={documentClass} onChange={(event) => setDocumentClass(event.target.value as typeof documentClass)}><option value="INTERNAL">Internal controlled</option><option value="EXTERNAL">External technical data</option><option value="RECORD">Record or evidence</option></select></label>
    <label className="wide"><span>Title</span><input value={title} onChange={(event) => setTitle(event.target.value)} required /></label>
    <label><span>Publication type</span><input value={manualType} onChange={(event) => setManualType(event.target.value)} required /></label>
    <label><span>Legacy owner role</span><input value={ownerRole} onChange={(event) => setOwnerRole(event.target.value)} required /></label>
    <label><span>Owner department</span><input value={ownerDepartment} onChange={(event) => setOwnerDepartment(event.target.value)} required /></label>
    <label><span>Language</span><input value={language} onChange={(event) => setLanguage(event.target.value)} required /></label>
    <label><span>Criticality</span><select value={criticality} onChange={(event) => setCriticality(event.target.value as typeof criticality)}><option value="STANDARD">Standard</option><option value="IMPORTANT">Important</option><option value="CRITICAL">Critical</option></select></label>
    <label><span>Review interval (months)</span><input type="number" min={1} max={120} value={reviewInterval} onChange={(event) => setReviewInterval(event.target.value)} required /></label>
    <label><span>Next review due</span><input type="date" value={nextReview} onChange={(event) => setNextReview(event.target.value)} /></label>
    <label><span><input type="checkbox" checked={regulated} onChange={(event) => setRegulated(event.target.checked)} /> Regulated document</span></label>
    <label><span><input type="checkbox" checked={restricted} onChange={(event) => setRestricted(event.target.checked)} /> Restricted access</span></label>
    <label><span><input type="checkbox" checked={authority} onChange={(event) => setAuthority(event.target.checked)} /> Authority approval required</span></label>
    <label><span><input type="checkbox" checked={ackRequired} onChange={(event) => setAckRequired(event.target.checked)} /> Acknowledgement required</span></label>
    <FormError message={mutation.error} />
    <div className="dc-form__actions"><button type="submit" className="dc-button dc-button--primary" disabled={mutation.busy}><Save size={14} /> {mutation.busy ? "Saving…" : "Save document controls"}</button></div>
  </form>;
}

function ChangeRequestForm({ detail, tenant, onChanged }: CommonProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("NORMAL");
  const [sourceModule, setSourceModule] = useState("DOCUMENT_CONTROL");
  const [sourceEntityType, setSourceEntityType] = useState("");
  const [sourceEntityId, setSourceEntityId] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [trainingImpact, setTrainingImpact] = useState(false);
  const [qmsBlocking, setQmsBlocking] = useState(false);
  const mutation = useMutation(onChanged);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void mutation.run(() => createDocumentChangeRequest(tenant, {
      manual_id: detail.document.id,
      revision_id: detail.document.latest_revision?.id || null,
      source_module: sourceModule,
      source_entity_type: sourceEntityType || null,
      source_entity_id: sourceEntityId || null,
      title,
      description,
      priority,
      due_at: dueAt ? new Date(dueAt).toISOString() : null,
      impact: {},
      training_impact_required: trainingImpact,
      qms_blocking: qmsBlocking,
    }));
  };
  return <form className="dc-form" onSubmit={submit}><label><span>Source module</span><select value={sourceModule} onChange={(event) => setSourceModule(event.target.value)}><option>DOCUMENT_CONTROL</option><option>QMS</option><option>TRAINING</option><option>PLANNING</option><option>PRODUCTION</option><option>MAINTENANCE</option><option>FLEET</option><option>STORES</option><option>TECHNICAL_RECORDS</option></select></label><label><span>Priority</span><select value={priority} onChange={(event) => setPriority(event.target.value)}><option>LOW</option><option>NORMAL</option><option>HIGH</option><option>CRITICAL</option></select></label><label className="wide"><span>Change title</span><input value={title} onChange={(event) => setTitle(event.target.value)} required /></label><label className="wide"><span>Description and required outcome</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} required /></label><label><span>Source entity type</span><input value={sourceEntityType} onChange={(event) => setSourceEntityType(event.target.value)} placeholder="Audit finding, CAR, work order…" /></label><label><span>Source entity ID</span><input value={sourceEntityId} onChange={(event) => setSourceEntityId(event.target.value)} /></label><label><span>Due date</span><input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} /></label><label><span><input type="checkbox" checked={trainingImpact} onChange={(event) => setTrainingImpact(event.target.checked)} /> Training impact required</span></label><label><span><input type="checkbox" checked={qmsBlocking} onChange={(event) => setQmsBlocking(event.target.checked)} /> QMS item blocks publication</span></label><FormError message={mutation.error} /><div className="dc-form__actions"><button className="dc-button dc-button--primary" type="submit" disabled={mutation.busy}><Plus size={14} /> Create change request</button></div></form>;
}

function WorkflowControls({ detail, tenant, onChanged }: CommonProps) {
  const latest = detail.document.latest_revision;
  const workflow = detail.workflows[0];
  const mutation = useMutation(onChanged);
  const [comments, setComments] = useState("");
  const [effectiveAt, setEffectiveAt] = useState("");
  const [training, setTraining] = useState(workflow?.training_readiness_status || "NOT_REQUIRED");
  const [qms, setQms] = useState(workflow?.qms_readiness_status || "NOT_REQUIRED");
  const [distribution, setDistribution] = useState(workflow?.distribution_readiness_status || "NOT_REQUIRED");
  if (!latest) return <div className="dc-empty"><strong>No revision exists</strong><p>Upload a source revision before creating a workflow.</p></div>;
  if (!workflow) return <div className="dc-form"><div className="dc-form__actions"><button type="button" className="dc-button dc-button--primary" disabled={mutation.busy || latest.immutable} onClick={() => void mutation.run(() => createDocumentWorkflow(tenant, { manual_id: detail.document.id, revision_id: latest.id, requires_authority: detail.document.profile.requires_authority_approval, training_impact_required: false, training_readiness_status: "NOT_REQUIRED", qms_readiness_status: "NOT_REQUIRED", distribution_readiness_status: "NOT_REQUIRED" }))}><Play size={14} /> Start revision workflow</button></div><FormError message={mutation.error} /></div>;
  const actions = WORKFLOW_ACTIONS[workflow.state] || [];
  return <div className="dc-form"><label className="wide"><span>Decision comments</span><textarea value={comments} onChange={(event) => setComments(event.target.value)} /></label><label><span>Training readiness</span><ReadinessSelect value={training} onChange={setTraining} /></label><label><span>QMS readiness</span><ReadinessSelect value={qms} onChange={setQms} /></label><label><span>Distribution readiness</span><ReadinessSelect value={distribution} onChange={setDistribution} /></label><label><span>Effectivity time</span><input type="datetime-local" value={effectiveAt} onChange={(event) => setEffectiveAt(event.target.value)} /></label><FormError message={mutation.error} /><div className="dc-form__actions">{actions.map((item) => <button type="button" key={item.action} className={`dc-button ${item.danger ? "dc-button--danger" : "dc-button--primary"}`} disabled={mutation.busy} onClick={() => void mutation.run(() => transitionDocumentWorkflow(tenant, workflow.id, { action: item.action, comments: comments || null, evidence: [], expected_version: workflow.version, effective_at: effectiveAt ? new Date(effectiveAt).toISOString() : undefined, training_readiness_status: training, qms_readiness_status: qms, distribution_readiness_status: distribution }))}>{item.label}</button>)}</div></div>;
}

function ReadinessSelect({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return <select value={value} onChange={(event) => onChange(event.target.value)}><option>NOT_REQUIRED</option><option>PENDING</option><option>BLOCKED</option><option>READY</option><option>WAIVED</option></select>;
}

function AuthorityForm({ detail, tenant, onChanged }: CommonProps) {
  const [authorityName, setAuthorityName] = useState("Kenya Civil Aviation Authority");
  const [reference, setReference] = useState("");
  const [responseDue, setResponseDue] = useState("");
  const mutation = useMutation(onChanged);
  const revision = detail.document.latest_revision;
  const workflow = detail.workflows[0];
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!revision) return;
    void mutation.run(() => createAuthoritySubmission(tenant, { manual_id: detail.document.id, revision_id: revision.id, workflow_id: workflow?.id || null, authority_name: authorityName, submission_reference: reference, response_due_at: responseDue ? new Date(responseDue).toISOString() : null, evidence: [] }));
  };
  return <form className="dc-form" onSubmit={submit}><label><span>Authority</span><input value={authorityName} onChange={(event) => setAuthorityName(event.target.value)} required /></label><label><span>Submission reference</span><input value={reference} onChange={(event) => setReference(event.target.value)} required /></label><label><span>Response due</span><input type="datetime-local" value={responseDue} onChange={(event) => setResponseDue(event.target.value)} /></label><FormError message={mutation.error} /><div className="dc-form__actions"><button type="submit" className="dc-button dc-button--primary" disabled={mutation.busy || !revision}><Send size={14} /> Create submission record</button></div></form>;
}

function TemporaryRevisionForm({ detail, tenant, onChanged }: CommonProps) {
  const current = detail.document.latest_revision;
  const [number, setNumber] = useState("");
  const [title, setTitle] = useState("");
  const [reason, setReason] = useState("");
  const [effective, setEffective] = useState("");
  const [expiry, setExpiry] = useState("");
  const mutation = useMutation(onChanged);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!current) return;
    void mutation.run(() => createTemporaryRevision(tenant, { manual_id: detail.document.id, base_revision_id: current.id, tr_number: number, title, reason, affected_sections: [], effective_date: effective, expiry_date: expiry }));
  };
  return <form className="dc-form" onSubmit={submit}><label><span>TR number</span><input value={number} onChange={(event) => setNumber(event.target.value)} required /></label><label><span>Effective date</span><input type="date" value={effective} onChange={(event) => setEffective(event.target.value)} required /></label><label className="wide"><span>Subject</span><input value={title} onChange={(event) => setTitle(event.target.value)} required /></label><label className="wide"><span>Reason and filing instruction</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} required /></label><label><span>Expiry or incorporation due</span><input type="date" value={expiry} onChange={(event) => setExpiry(event.target.value)} required /></label><FormError message={mutation.error} /><div className="dc-form__actions"><button type="submit" className="dc-button dc-button--primary" disabled={mutation.busy || !current}><FilePlus2 size={14} /> Create temporary revision</button></div></form>;
}

function DistributionForm({ detail, tenant, onChanged }: CommonProps) {
  const revision = detail.document.latest_revision;
  const [title, setTitle] = useState("");
  const [recipientIds, setRecipientIds] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [ackRequired, setAckRequired] = useState(true);
  const mutation = useMutation(onChanged);
  const recipients = useMemo(() => recipientIds.split(/[\s,;]+/).map((value) => value.trim()).filter(Boolean), [recipientIds]);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!revision) return;
    void mutation.run(() => createDistributionCampaign(tenant, { manual_id: detail.document.id, revision_id: revision.id, title, audience: { source: "manual-selection" }, acknowledgement_required: ackRequired, due_at: dueAt ? new Date(dueAt).toISOString() : null, recipient_user_ids: recipients, metadata: {} }));
  };
  return <form className="dc-form" onSubmit={submit}><label className="wide"><span>Campaign title</span><input value={title} onChange={(event) => setTitle(event.target.value)} required /></label><label className="wide"><span>Recipient user IDs</span><textarea value={recipientIds} onChange={(event) => setRecipientIds(event.target.value)} placeholder="Paste active tenant user IDs separated by commas or spaces" required /></label><label><span>Due date</span><input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} /></label><label><span><input type="checkbox" checked={ackRequired} onChange={(event) => setAckRequired(event.target.checked)} /> Read-and-understand acknowledgement required</span></label><FormError message={mutation.error} /><div className="dc-form__actions"><button type="submit" className="dc-button" disabled={mutation.busy || !revision || !recipients.length}><Plus size={14} /> Create draft campaign</button>{detail.distribution_campaigns.filter((row) => row.status === "DRAFT" || row.status === "READY").map((row) => <button type="button" key={row.id} className="dc-button dc-button--primary" disabled={mutation.busy} onClick={() => void mutation.run(() => issueDistributionCampaign(tenant, row.id, { recipient_user_ids: recipients, due_at: dueAt ? new Date(dueAt).toISOString() : null }))}><Send size={14} /> Issue {row.title}</button>)}</div></form>;
}

function ApplicabilityForm({ detail, tenant, onChanged }: CommonProps) {
  const [targetType, setTargetType] = useState("AIRCRAFT_TYPE");
  const [targetId, setTargetId] = useState("");
  const [targetValue, setTargetValue] = useState("");
  const [ruleType, setRuleType] = useState("INCLUDE");
  const mutation = useMutation(onChanged);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void mutation.run(() => createApplicabilityRule(tenant, { manual_id: detail.document.id, revision_id: detail.document.latest_revision?.id || null, rule_type: ruleType, target_type: targetType, target_id: targetId || null, target_value: targetValue || null, source: "MANUAL", criteria: {} }));
  };
  return <form className="dc-form" onSubmit={submit}><label><span>Rule</span><select value={ruleType} onChange={(event) => setRuleType(event.target.value)}><option>INCLUDE</option><option>EXCLUDE</option><option>WARNING</option></select></label><label><span>Target type</span><select value={targetType} onChange={(event) => setTargetType(event.target.value)}><option>AIRCRAFT_TYPE</option><option>AIRCRAFT</option><option>SERIAL_RANGE</option><option>ENGINE_TYPE</option><option>COMPONENT_TYPE</option><option>BASE</option><option>DEPARTMENT</option><option>ROLE</option><option>AUTHORIZATION_GROUP</option><option>WORK_ORDER</option><option>WORK_PACKAGE</option></select></label><label><span>Canonical target ID</span><input value={targetId} onChange={(event) => setTargetId(event.target.value)} /></label><label><span>Target value or range</span><input value={targetValue} onChange={(event) => setTargetValue(event.target.value)} /></label><FormError message={mutation.error} /><div className="dc-form__actions"><button type="submit" className="dc-button dc-button--primary" disabled={mutation.busy || (!targetId && !targetValue)}><Plus size={14} /> Add applicability rule</button></div></form>;
}

function ControlledCopyForm({ detail, tenant, onChanged }: CommonProps) {
  const published = detail.revisions.find((revision) => revision.status === "PUBLISHED");
  const [copyNumber, setCopyNumber] = useState("");
  const [location, setLocation] = useState("");
  const [holderName, setHolderName] = useState("");
  const mutation = useMutation(onChanged);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!published) return;
    void mutation.run(() => createControlledCopy(tenant, { manual_id: detail.document.id, revision_id: published.id, copy_number: copyNumber, format: "HARDCOPY", holder_name: holderName || null, location_text: location, metadata: {} }));
  };
  return <form className="dc-form" onSubmit={submit}><label><span>Copy number</span><input value={copyNumber} onChange={(event) => setCopyNumber(event.target.value)} required /></label><label><span>Holder name</span><input value={holderName} onChange={(event) => setHolderName(event.target.value)} /></label><label className="wide"><span>Physical location</span><input value={location} onChange={(event) => setLocation(event.target.value)} required /></label><FormError message={mutation.error || (!published ? "A published revision is required before issuing a controlled copy." : "")} /><div className="dc-form__actions"><button type="submit" className="dc-button dc-button--primary" disabled={mutation.busy || !published}><Plus size={14} /> Issue controlled copy</button></div></form>;
}

function ReviewForm({ detail, tenant, onChanged }: CommonProps) {
  const [dueAt, setDueAt] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const mutation = useMutation(onChanged);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void mutation.run(() => createDocumentReview(tenant, { manual_id: detail.document.id, revision_id: detail.document.current_published_revision_id || detail.document.latest_revision?.id || null, owner_user_id: ownerId || null, due_at: new Date(dueAt).toISOString() }));
  };
  return <form className="dc-form" onSubmit={submit}><label><span>Review due</span><input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} required /></label><label><span>Owner user ID</span><input value={ownerId} onChange={(event) => setOwnerId(event.target.value)} /></label><FormError message={mutation.error} /><div className="dc-form__actions"><button type="submit" className="dc-button dc-button--primary" disabled={mutation.busy}><Plus size={14} /> Schedule review</button></div></form>;
}

function IntegrationForm({ detail, tenant, onChanged }: CommonProps) {
  const [module, setModule] = useState("QMS");
  const [entityType, setEntityType] = useState("");
  const [entityId, setEntityId] = useState("");
  const [relation, setRelation] = useState("CHANGE_DRIVER");
  const [status, setStatus] = useState("");
  const [blocking, setBlocking] = useState(false);
  const mutation = useMutation(onChanged);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void mutation.run(() => createIntegrationLink(tenant, { manual_id: detail.document.id, revision_id: detail.document.latest_revision?.id || null, workflow_id: detail.workflows[0]?.id || null, source_module: module, entity_type: entityType, entity_id: entityId, relation_type: relation, blocking, status_snapshot: status || null, metadata: {} }));
  };
  return <form className="dc-form" onSubmit={submit}><label><span>Source module</span><select value={module} onChange={(event) => setModule(event.target.value)}><option>QMS</option><option>TRAINING</option><option>WORKFORCE</option><option>PLANNING</option><option>PRODUCTION</option><option>MAINTENANCE</option><option>FLEET</option><option>STORES</option><option>TECHNICAL_RECORDS</option></select></label><label><span>Relationship</span><select value={relation} onChange={(event) => setRelation(event.target.value)}><option>CHANGE_DRIVER</option><option>BLOCKER</option><option>TRAINING_IMPACT</option><option>APPLICABILITY</option><option>USED_BY</option><option>EVIDENCE</option><option>SOURCE</option><option>COMPLIANCE</option></select></label><label><span>Entity type</span><input value={entityType} onChange={(event) => setEntityType(event.target.value)} required /></label><label><span>Canonical entity ID</span><input value={entityId} onChange={(event) => setEntityId(event.target.value)} required /></label><label><span>Status snapshot</span><input value={status} onChange={(event) => setStatus(event.target.value)} /></label><label><span><input type="checkbox" checked={blocking} onChange={(event) => setBlocking(event.target.checked)} /> Blocks publication</span></label><FormError message={mutation.error} /><div className="dc-form__actions"><button type="submit" className="dc-button dc-button--primary" disabled={mutation.busy}><Plus size={14} /> Link module record</button></div></form>;
}

function ExternalSourceForm({ detail, tenant, onChanged }: CommonProps) {
  const [provider, setProvider] = useState("");
  const [authority, setAuthority] = useState("");
  const [reference, setReference] = useState("");
  const [url, setUrl] = useState("");
  const [method, setMethod] = useState("MANUAL_CHECK");
  const [nextCheck, setNextCheck] = useState("");
  const mutation = useMutation(onChanged);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void mutation.run(() => createExternalSource(tenant, { manual_id: detail.document.id, provider, authority: authority || null, subscription_reference: reference || null, access_url: url || null, update_method: method, next_check_due_at: nextCheck ? new Date(nextCheck).toISOString() : null, metadata: {} }));
  };
  return <form className="dc-form" onSubmit={submit}><label><span>Provider</span><input value={provider} onChange={(event) => setProvider(event.target.value)} required /></label><label><span>Authority</span><input value={authority} onChange={(event) => setAuthority(event.target.value)} /></label><label><span>Subscription reference</span><input value={reference} onChange={(event) => setReference(event.target.value)} /></label><label><span>Update method</span><select value={method} onChange={(event) => setMethod(event.target.value)}><option>MANUAL_CHECK</option><option>EMAIL</option><option>PORTAL</option><option>API</option><option>SUBSCRIPTION</option></select></label><label className="wide"><span>Access URL</span><input value={url} onChange={(event) => setUrl(event.target.value)} /></label><label><span>Next currency check</span><input type="datetime-local" value={nextCheck} onChange={(event) => setNextCheck(event.target.value)} /></label><FormError message={mutation.error || (detail.document.profile.document_class !== "EXTERNAL" ? "Set the document class to EXTERNAL before registering its technical-data source." : "")} /><div className="dc-form__actions"><button type="submit" className="dc-button dc-button--primary" disabled={mutation.busy || detail.document.profile.document_class !== "EXTERNAL"}><Plus size={14} /> Register external source</button></div></form>;
}

type CommonProps = { detail: DocumentDetailResponse; tenant: string; onChanged: () => void };
