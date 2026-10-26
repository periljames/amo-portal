import React, { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  BadgeCheck,
  Ban,
  Building2,
  CalendarClock,
  CheckCircle2,
  ChevronRight,
  FileCheck2,
  FileText,
  Link2,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  X,
} from "lucide-react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import {getCachedUser} from "../../services/auth";
import { isTenantAdmin } from "../../utils/tenantAccess";

import {
  createExternalProvider,
  createProviderContract,
  createProviderEvidence,
  decideProviderEvidence,
  getExternalProvider,
  getExternalProviders,
  getProviderGovernanceSummary,
  transitionExternalProvider,
  transitionProviderContract,
  type ContractStatus,
  type EvidenceStatus,
  type ProviderContract,
  type ProviderDetail,
  type ProviderGovernanceSummary,
  type ProviderKind,
  type ProviderListItem,
  type ProviderRisk,
  type ProviderStatus,
} from "../../services/qmsProviders";
import "../../styles/qms-external-providers.css";
import ProviderQualificationWorkspace from "./ProviderQualificationWorkspace";
import ProviderAgreementControls from "./ProviderAgreementControls";
import ProviderAgreementsWorkspace from "./ProviderAgreementsWorkspace";
import { hasQmsRolePermission } from "../../app/routeGuards";
import { canAccessDepartment, getAssignedDepartment } from "../../utils/departmentAccess";
import { getContext } from "../../services/auth";
import { Link } from "react-router-dom";
import ProviderAlertSettingsPanel from "../../components/notifications/ProviderAlertSettingsPanel";
import ProviderOversight, { ProviderPortfolio } from "./ProviderOversight";
import QmsRegisterPage from "./QmsRegisterPage";

const PROVIDER_KINDS: ProviderKind[] = [
  "SUPPLIER",
  "CONTRACTOR",
  "SUBCONTRACTOR",
  "SERVICE_PROVIDER",
  "CONSULTANT",
  "LABORATORY",
  "CALIBRATION_PROVIDER",
  "OTHER",
];
const PROVIDER_STATUSES: ProviderStatus[] = [
  "PROSPECTIVE",
  "UNDER_REVIEW",
  "CONDITIONALLY_APPROVED",
  "APPROVED",
  "RESTRICTED",
  "SUSPENDED",
  "EXPIRED",
  "REJECTED",
  "ARCHIVED",
];
const PROVIDER_RISKS: ProviderRisk[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

type DetailTab = "overview" | "approval" | "contracts" | "evidence" | "monitoring" | "qualification";

function titleCase(value: string | null | undefined): string {
  return String(value || "")
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function dateLabel(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(`${value.slice(0, 10)}T00:00:00`);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short", day: "numeric" }).format(date);
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "The governed provider operation could not be completed.";
}

function statusTone(status: string): string {
  const value = status.toUpperCase();
  if (["APPROVED", "ACTIVE", "VERIFIED"].includes(value)) return "positive";
  if (["SUSPENDED", "REJECTED", "TERMINATED", "EXPIRED"].includes(value)) return "negative";
  if (["RESTRICTED", "CONDITIONALLY_APPROVED", "UNDER_REVIEW", "PENDING"].includes(value)) return "warning";
  return "neutral";
}

function StatusPill({ value }: { value: string }): React.ReactElement {
  return <span className={`qms-provider-status is-${statusTone(value)}`}>{titleCase(value)}</span>;
}

function SummaryCard({ icon: Icon, label, value, alert = false }: {
  icon: React.ComponentType<{ size?: number }>;
  label: string;
  value: number;
  alert?: boolean;
}): React.ReactElement {
  return (
    <div className={`qms-provider-summary-card${alert && value ? " is-alert" : ""}`}>
      <Icon size={18} />
      <div>
        <strong>{value}</strong>
        <span>{label}</span>
      </div>
    </div>
  );
}

function ProviderCreatePanel({ amoCode, onCreated, onClose }: {
  amoCode: string;
  onCreated: (provider: ProviderDetail) => void;
  onClose: () => void;
}): React.ReactElement {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    supplier_code: "",
    legal_name: "",
    trading_name: "",
    provider_kind: "SUPPLIER" as ProviderKind,
    risk_level: "MEDIUM" as ProviderRisk,
    quality_contact_name: "",
    quality_contact_email: "",
    country: "",
    contract_required: false,
    review_interval_days: 365,
    scope_summary: "",
    quality_requirements: "",
  });

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const created = await createExternalProvider(amoCode, {
        ...form,
        trading_name: form.trading_name || null,
        quality_contact_name: form.quality_contact_name || null,
        quality_contact_email: form.quality_contact_email || null,
        country: form.country || null,
        scope_summary: form.scope_summary || null,
        quality_requirements: form.quality_requirements || null,
      });
      onCreated(created);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="qms-provider-editor" aria-labelledby="provider-create-title">
      <div className="qms-provider-editor__header">
        <div>
          <span className="qms-provider-eyebrow">Controlled registration</span>
          <h2 id="provider-create-title">Add external provider</h2>
          <p>Create the shared provider identity, then govern scope, contracts and evidence in Quality.</p>
        </div>
        <button type="button" className="qms-provider-icon-button" onClick={onClose} aria-label="Close provider form"><X size={18} /></button>
      </div>
      {error && <div className="qms-provider-alert is-error"><AlertTriangle size={17} />{error}</div>}
      <form className="qms-provider-form" onSubmit={submit}>
        <label>Provider code<input required minLength={2} maxLength={64} spellCheck={false} value={form.supplier_code} onChange={(e) => setForm({ ...form, supplier_code: e.target.value })} /></label>
        <label className="is-wide">Legal name<input required minLength={2} maxLength={255} value={form.legal_name} onChange={(e) => setForm({ ...form, legal_name: e.target.value })} /></label>
        <label>Trading name<input value={form.trading_name} onChange={(e) => setForm({ ...form, trading_name: e.target.value })} /></label>
        <label>Provider type<select value={form.provider_kind} onChange={(e) => setForm({ ...form, provider_kind: e.target.value as ProviderKind })}>{PROVIDER_KINDS.map((item) => <option key={item} value={item}>{titleCase(item)}</option>)}</select></label>
        <label>Risk<select value={form.risk_level} onChange={(e) => setForm({ ...form, risk_level: e.target.value as ProviderRisk })}>{PROVIDER_RISKS.map((item) => <option key={item}>{item}</option>)}</select></label>
        <label>Quality contact<input value={form.quality_contact_name} onChange={(e) => setForm({ ...form, quality_contact_name: e.target.value })} /></label>
        <label>Quality email<input type="email" value={form.quality_contact_email} onChange={(e) => setForm({ ...form, quality_contact_email: e.target.value })} /></label>
        <label>Country<input value={form.country} onChange={(e) => setForm({ ...form, country: e.target.value })} /></label>
        <label>Review interval (30–365 days)<input type="number" required min={30} max={365} value={form.review_interval_days} onChange={(e) => setForm({ ...form, review_interval_days: Number(e.target.value) })} /></label>
        <label className="is-wide">Approved / proposed scope<textarea value={form.scope_summary} onChange={(e) => setForm({ ...form, scope_summary: e.target.value })} /></label>
        <label className="is-wide">Quality requirements<textarea value={form.quality_requirements} onChange={(e) => setForm({ ...form, quality_requirements: e.target.value })} /></label>
        <label className="qms-provider-check is-wide"><input type="checkbox" checked={form.contract_required} onChange={(e) => setForm({ ...form, contract_required: e.target.checked })} />A current contract is mandatory before Quality approval</label>
        <div className="qms-provider-form__actions is-wide">
          <button type="button" className="qms-provider-button is-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="qms-provider-button" disabled={saving}>{saving ? "Creating…" : "Create provider"}</button>
        </div>
      </form>
    </section>
  );
}

function ContractPanel({ amoCode, provider, onChanged }: {
  amoCode: string;
  provider: ProviderDetail;
  onChanged: () => Promise<void>;
}): React.ReactElement {
  const canManage = hasQmsRolePermission("qms.supplier.manage");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ contract_number: "", title: "", scope_text: "", effective_on: "", expires_on: "", termination_notice_days: "", supersedes_contract_id: "", change_reason: "" });

  const create = async (event: FormEvent) => {
    event.preventDefault();
    if (!canManage) return;
    setBusy("create");
    setError(null);
    try {
      await createProviderContract(amoCode, provider.id, {
        contract_number: form.contract_number,
        title: form.title,
        scope_text: form.scope_text,
        effective_on: form.effective_on || null,
        expires_on: form.expires_on || null,
        termination_notice_days: form.termination_notice_days ? Number(form.termination_notice_days) : null,
        supersedes_contract_id: form.supersedes_contract_id || null,
        change_reason: form.supersedes_contract_id ? form.change_reason : null,
      });
      setForm({ contract_number: "", title: "", scope_text: "", effective_on: "", expires_on: "", termination_notice_days: "", supersedes_contract_id: "", change_reason: "" });
      setOpen(false);
      await onChanged();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const transition = async (contract: ProviderContract, target: ContractStatus) => {
    if (!canManage) return;
    const reason = window.prompt(`Reason for changing ${contract.contract_number} to ${titleCase(target)}:`)?.trim();
    if (!reason || reason.length < 8) return;
    setBusy(contract.id);
    setError(null);
    try {
      await transitionProviderContract(amoCode, provider.id, contract.id, { expected_version: contract.version, target_status: target, reason });
      await onChanged();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="qms-provider-detail-section">
      <div className="qms-provider-section-heading">
        <div><span className="qms-provider-eyebrow">Agreement control</span><h3>Contracts</h3></div>
        {canManage && <button type="button" className="qms-provider-button is-secondary" onClick={() => setOpen((value) => !value)}><Plus size={16} />Add contract</button>}
      </div>
      {error && <div className="qms-provider-alert is-error"><AlertTriangle size={17} />{error}</div>}
      {open && canManage && (
        <form className="qms-provider-form qms-provider-inline-form" onSubmit={create}>
          <label>Contract number<input required value={form.contract_number} onChange={(e) => setForm({ ...form, contract_number: e.target.value })} /></label>
          <label>Title<input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
          <label className="is-wide">Amend or renew an earlier agreement (optional)
            <select value={form.supersedes_contract_id} onChange={(e) => setForm({ ...form, supersedes_contract_id: e.target.value, change_reason: "" })}>
              <option value="">New independent agreement</option>
              {provider.contracts.filter(c => c.status !== "DRAFT").map(c => <option key={c.id} value={c.id}>{c.contract_number} · {c.title}</option>)}
            </select></label>
          {form.supersedes_contract_id && <label className="is-wide">Documented reason for amendment or renewal
            <textarea minLength={8} required value={form.change_reason} onChange={(e) => setForm({ ...form, change_reason: e.target.value })} />
          </label>}
          <label className="is-wide">Controlled scope<textarea required value={form.scope_text} onChange={(e) => setForm({ ...form, scope_text: e.target.value })} /></label>
          <label>Effective date<input type="date" value={form.effective_on} onChange={(e) => setForm({ ...form, effective_on: e.target.value })} /></label>
          <label>Expiry date<input type="date" value={form.expires_on} onChange={(e) => setForm({ ...form, expires_on: e.target.value })} /></label>
          <label>Termination notice (days)<input type="number" min={0} value={form.termination_notice_days} onChange={(e) => setForm({ ...form, termination_notice_days: e.target.value })} /></label>
          <div className="qms-provider-form__actions"><button type="submit" className="qms-provider-button" disabled={busy === "create"}>{busy === "create" ? "Saving…" : "Save draft"}</button></div>
        </form>
      )}
      <div className="qms-provider-record-list">
        {provider.contracts.length === 0 && <div className="qms-provider-empty">No governed contracts are linked to this provider.</div>}
        {provider.contracts.map((contract) => (
          <article key={contract.id} className="qms-provider-record">
            <FileText size={19} />
            <div className="qms-provider-record__body">
              <div className="qms-provider-record__title"><strong>{contract.contract_number}</strong><span>{contract.title}</span><StatusPill value={contract.effective_status} /></div>
              <p>{contract.scope_text}</p>
              <div className="qms-provider-meta"><span>Effective {dateLabel(contract.effective_on)}</span><span>Expires {dateLabel(contract.expires_on)}</span>{contract.termination_notice_days != null && <span>{contract.termination_notice_days} day notice</span>}</div>
              {contract.supersedes_contract_id && <p>Supersedes prior agreement: {provider.contracts.find(item => item.id === contract.supersedes_contract_id)?.contract_number || contract.supersedes_contract_id}</p>}
              {contract.change_reason && <p>Amendment / renewal reason: {contract.change_reason}</p>}
            </div>
            {canManage && <div className="qms-provider-record__actions">
              {contract.status === "DRAFT" && <button disabled={busy === contract.id || !contract.controlled_document_id || !contract.controlled_document_revision || !contract.signed_evidence_submission_id} title="Link an executed published DMS revision with signed QMS evidence before requesting Quality activation" onClick={() => transition(contract, "ACTIVE")}>Activate with Quality approval</button>}
              {contract.status === "ACTIVE" && <button disabled={busy === contract.id} onClick={() => transition(contract, "SUSPENDED")}>Suspend</button>}
              {["ACTIVE", "SUSPENDED"].includes(contract.status) && <button disabled={busy === contract.id} onClick={() => transition(contract, "TERMINATED")}>Terminate</button>}
              {["ACTIVE", "SUSPENDED", "EXPIRED"].includes(contract.status) && provider.contracts.some((successor) => successor.supersedes_contract_id === contract.id && successor.effective_status === "ACTIVE") && <button disabled={busy === contract.id} onClick={() => transition(contract, "SUPERSEDED")}>Supersede with active renewal</button>}
            </div>}
            {canManage && <ProviderAgreementControls amoCode={amoCode} contract={contract} onChanged={onChanged} />}
          </article>
        ))}
      </div>
    </div>
  );
}

function EvidencePanel({ amoCode, provider, onChanged }: {
  amoCode: string;
  provider: ProviderDetail;
  onChanged: () => Promise<void>;
}): React.ReactElement {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ evidence_type: "CERTIFICATE", source_system: "DOCUMENT_CONTROL", source_id: "", title: "", valid_from: "", valid_until: "" });

  const create = async (event: FormEvent) => {
    event.preventDefault();
    setBusy("create");
    setError(null);
    try {
      await createProviderEvidence(amoCode, provider.id, {
        ...form,
        valid_from: form.valid_from || null,
        valid_until: form.valid_until || null,
      });
      setForm({ evidence_type: "CERTIFICATE", source_system: "DOCUMENT_CONTROL", source_id: "", title: "", valid_from: "", valid_until: "" });
      setOpen(false);
      await onChanged();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const decide = async (evidenceId: string, target: EvidenceStatus) => {
    const reason = window.prompt(`Reason for marking this evidence ${titleCase(target)}:`)?.trim();
    if (!reason || reason.length < 8) return;
    setBusy(evidenceId);
    setError(null);
    try {
      await decideProviderEvidence(amoCode, provider.id, evidenceId, { target_status: target, reason });
      await onChanged();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="qms-provider-detail-section">
      <div className="qms-provider-section-heading">
        <div><span className="qms-provider-eyebrow">Objective evidence</span><h3>Provider evidence</h3></div>
        <button type="button" className="qms-provider-button is-secondary" onClick={() => setOpen((value) => !value)}><Link2 size={16} />Link evidence</button>
      </div>
      {error && <div className="qms-provider-alert is-error"><AlertTriangle size={17} />{error}</div>}
      {open && (
        <form className="qms-provider-form qms-provider-inline-form" onSubmit={create}>
          <label>Evidence type<input required value={form.evidence_type} onChange={(e) => setForm({ ...form, evidence_type: e.target.value })} /></label>
          <label>Source system<input required value={form.source_system} onChange={(e) => setForm({ ...form, source_system: e.target.value })} /></label>
          <label>Source record / revision<input required value={form.source_id} onChange={(e) => setForm({ ...form, source_id: e.target.value })} /></label>
          <label>Title<input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
          <label>Valid from<input type="date" value={form.valid_from} onChange={(e) => setForm({ ...form, valid_from: e.target.value })} /></label>
          <label>Valid until<input type="date" value={form.valid_until} onChange={(e) => setForm({ ...form, valid_until: e.target.value })} /></label>
          <div className="qms-provider-form__actions is-wide"><button type="submit" className="qms-provider-button" disabled={busy === "create"}>{busy === "create" ? "Linking…" : "Link evidence"}</button></div>
        </form>
      )}
      <div className="qms-provider-record-list">
        {provider.evidence.length === 0 && <div className="qms-provider-empty">No controlled evidence is linked to this provider.</div>}
        {provider.evidence.map((item) => (
          <article key={item.id} className="qms-provider-record">
            <FileCheck2 size={19} />
            <div className="qms-provider-record__body">
              <div className="qms-provider-record__title"><strong>{titleCase(item.evidence_type)}</strong><span>{item.title}</span><StatusPill value={item.effective_status} /></div>
              <div className="qms-provider-meta"><span>{item.source_system} · {item.source_id}</span><span>Valid until {dateLabel(item.valid_until)}</span></div>
            </div>
            <div className="qms-provider-record__actions">
              {item.status === "PENDING" && <button disabled={busy === item.id} onClick={() => decide(item.id, "VERIFIED")}>Verify</button>}
              {!(["REJECTED", "SUPERSEDED"] as string[]).includes(item.status) && <button disabled={busy === item.id} onClick={() => decide(item.id, "REJECTED")}>Reject</button>}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function ProviderDetailWorkspace({ amoCode, providerId, tab, onBack }: {
  amoCode: string;
  providerId: number;
  tab: DetailTab;
  onBack: () => void;
}): React.ReactElement {
  const navigate = useNavigate();
  const qualityManager=isTenantAdmin(getCachedUser()) || getCachedUser()?.role==="QUALITY_MANAGER";
  const [provider, setProvider] = useState<ProviderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [transitionReason, setTransitionReason] = useState("");
  const [transitionTarget, setTransitionTarget] = useState<ProviderStatus | "">("");
  const [transitioning, setTransitioning] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setProvider(await getExternalProvider(amoCode, providerId));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [amoCode, providerId]);

  useEffect(() => { void load(); }, [load]);

  const basePath = `/maintenance/${encodeURIComponent(amoCode)}/quality/suppliers/${providerId}`;
  const transition = async () => {
    if (!provider || !transitionTarget || transitionReason.trim().length < 8) return;
    setTransitioning(true);
    setError(null);
    try {
      const changed = await transitionExternalProvider(amoCode, provider.id, {
        expected_version: provider.governance_version,
        target_status: transitionTarget,
        reason: transitionReason.trim(),
      });
      setProvider(changed);
      setTransitionReason("");
      setTransitionTarget("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setTransitioning(false);
    }
  };

  if (loading) return <div className="qms-provider-loading"><RefreshCw className="is-spinning" size={20} />Loading governed provider record…</div>;
  if (!provider) return <div className="qms-provider-alert is-error"><AlertTriangle size={17} />{error || "Provider record is unavailable."}</div>;

  const tabs: Array<[DetailTab, string]> = [["overview", "Overview"], ["approval", "Approval & scope"], ["contracts", "Contracts"], ["evidence", "Evidence"], ["monitoring", "Monitoring"], ["qualification", "Qualification & surveillance"]];
  const approvalBlocked = provider.contract_required && provider.active_contract_count === 0;

  return (
    <div className="qms-provider-detail">
      <button type="button" className="qms-provider-back" onClick={onBack}>← External providers</button>
      <header className="qms-provider-detail__header">
        <div className="qms-provider-detail__identity">
          <span className="qms-provider-eyebrow">{provider.supplier_code} · {titleCase(provider.provider_kind)}</span>
          <h1>{provider.legal_name}</h1>
          <div className="qms-provider-meta"><StatusPill value={provider.status} /><span>Risk {provider.risk_level}</span>{provider.country && <span>{provider.country}</span>}</div>
        </div>
        <div className="qms-provider-detail__health">
          <div><strong>{provider.active_scope_count}</strong><span>active scopes</span></div>
          <div className={approvalBlocked ? "is-alert" : ""}><strong>{provider.active_contract_count}</strong><span>active contracts</span></div>
          <div><strong>{provider.verified_evidence_count}</strong><span>verified evidence</span></div>
        </div>
      </header>
      {error && <div className="qms-provider-alert is-error"><AlertTriangle size={17} />{error}</div>}
      {approvalBlocked && <div className="qms-provider-alert is-warning"><ShieldAlert size={17} />A current active contract is required before this provider can be Quality-approved.</div>}
      <nav className="qms-provider-detail-tabs" aria-label="External provider record">
        {tabs.map(([id, label]) => <button key={id} className={tab === id ? "is-active" : ""} onClick={() => navigate(`${basePath}/${id}`)}>{label}</button>)}
      </nav>

      {tab === "overview" && <section className="qms-provider-detail-section" aria-label="Linked provider workflows">
        <div className="qms-provider-section-heading">
          <div><span className="qms-provider-eyebrow">Shared data · separate decisions</span>
            <h3>Authorized workspaces</h3></div>
        </div>
        <p>All workflows use this supplier identity. Quality remains responsible for approval, Procurement for orders, DMS for controlled originals and Maintenance for technical authorization. A link never grants additional privileges.</p>
        <nav className="qms-provider-scope-list" aria-label="Provider cross-module actions">
          <Link to={`${basePath}/contracts`}>Quality agreements and amendments</Link>
          <Link to={`${basePath}/qualification`}>Qualification and scope reviews</Link>
          <Link to={`${basePath}/evidence`}>Evidence decisions and expiry</Link>
          <Link to={`${basePath}/monitoring`}>Surveillance and provider oversight</Link>
          {hasQmsRolePermission("qms.audit.view") &&
            <Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/audits/register`}>QMS audits and findings</Link>}
          {hasQmsRolePermission("qms.car.view") &&
            <Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/cars/register`}>CAR / CAPA and effectiveness reviews</Link>}
          {hasQmsRolePermission("qms.audit.manage") &&
            <Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/external-accounts`}>Provider accounts and delegated access</Link>}
          {hasQmsRolePermission("qms.document.view") &&
            <Link to={`/maintenance/${encodeURIComponent(amoCode)}/doc-control/provider-evidence`}>Document Control: governed originals and retention</Link>}
          {canAccessDepartment(getCachedUser(), getAssignedDepartment(getCachedUser(), getContext().department), "procurement") &&
            <Link to={`/maintenance/${encodeURIComponent(amoCode)}/procurement/suppliers`}>Procurement: sourcing, contracts and receiving</Link>}
          {canAccessDepartment(getCachedUser(), getAssignedDepartment(getCachedUser(), getContext().department), "maintenance") &&
            <Link to={`/maintenance/${encodeURIComponent(amoCode)}/contracted-work`}>Maintenance: contracted work and technical closeout</Link>}
        </nav>
      </section>}
      {tab === "overview" && (
        <div className="qms-provider-detail-grid">
          <section className="qms-provider-detail-section">
            <div className="qms-provider-section-heading"><div><span className="qms-provider-eyebrow">Governed profile</span><h3>Provider control</h3></div></div>
            <dl className="qms-provider-definition-list">
              <div><dt>Provider type</dt><dd>{titleCase(provider.provider_kind)}</dd></div>
              <div><dt>Quality contact</dt><dd>{provider.quality_contact_name || provider.quality_contact_email || "Not assigned"}</dd></div>
              <div><dt>Oversight owner</dt><dd>{provider.oversight_owner_user_id ? "Assigned" : "Not assigned"}</dd></div>
              <div><dt>Review due</dt><dd className={provider.review_due ? "is-alert" : ""}>{dateLabel(provider.next_review_due_on)}</dd></div>
              <div><dt>Contract mandatory</dt><dd>{provider.contract_required ? "Yes" : "No"}</dd></div>
              <div><dt>Governance version</dt><dd>{provider.governance_version || "Legacy record"}</dd></div>
            </dl>
          </section>
          <section className="qms-provider-detail-section">
            <div className="qms-provider-section-heading"><div><span className="qms-provider-eyebrow">Lifecycle decision</span><h3>Change provider state</h3></div></div>
            {!qualityManager ? <div className="qms-provider-empty">Quality lifecycle approval and restriction are reserved for the appointed Quality Manager.</div> : provider.allowed_transitions.length === 0 ? <div className="qms-provider-empty">No further lifecycle transitions are available.</div> : (
              <div className="qms-provider-transition">
                <label>Next state<select value={transitionTarget} onChange={(e) => setTransitionTarget(e.target.value as ProviderStatus)}><option value="">Select state</option>{provider.allowed_transitions.map((item) => <option key={item} value={item}>{titleCase(item)}</option>)}</select></label>
                <label>Attributable reason<textarea value={transitionReason} onChange={(e) => setTransitionReason(e.target.value)} placeholder="Explain the approval, restriction, suspension or reinstatement decision." /></label>
                <button className="qms-provider-button" disabled={!transitionTarget || transitionReason.trim().length < 8 || transitioning} onClick={() => void transition()}>{transitioning ? "Applying…" : "Apply governed transition"}</button>
              </div>
            )}
          </section>
        </div>
      )}

      {tab === "approval" && (
        <div className="qms-provider-detail-section">
          <div className="qms-provider-section-heading"><div><span className="qms-provider-eyebrow">Approved capability</span><h3>Scope and restrictions</h3></div><StatusPill value={provider.status} /></div>
          {provider.scope_summary && <div className="qms-provider-narrative"><strong>Governed scope summary</strong><p>{provider.scope_summary}</p></div>}
          {provider.quality_requirements && <div className="qms-provider-narrative"><strong>Quality requirements</strong><p>{provider.quality_requirements}</p></div>}
          <div className="qms-provider-scope-list">
            {provider.approval_scopes.length === 0 && <div className="qms-provider-empty">No Procurement approval scopes are recorded. Approval requires a governed scope summary or an active scope.</div>}
            {provider.approval_scopes.map((scope) => (
              <article key={scope.id}><BadgeCheck size={18} /><div><strong>{scope.category} · {scope.product_family}</strong><span>{scope.site_code} · {scope.authority}</span>{scope.restrictions && <p>{scope.restrictions}</p>}</div><StatusPill value={scope.status} /></article>
            ))}
          </div>
        </div>
      )}

      {tab === "contracts" && <ContractPanel amoCode={amoCode} provider={provider} onChanged={load} />}
      {tab === "evidence" && <EvidencePanel amoCode={amoCode} provider={provider} onChanged={load} />}
      {tab === "qualification" && <ProviderQualificationWorkspace amoCode={amoCode} supplierId={provider.id} />}
      {tab === "monitoring" && (
        <div className="qms-provider-detail-grid">
          <ProviderOversight amoCode={amoCode} supplierId={providerId}
            evidenceOptions={provider.evidence.filter(e=>e.effective_status==="VERIFIED")
              .map(e=>({id:e.id,title:e.title}))} />
          <section className="qms-provider-detail-section"><div className="qms-provider-section-heading"><div><span className="qms-provider-eyebrow">Review cycle</span><h3>Oversight</h3></div></div><dl className="qms-provider-definition-list"><div><dt>Last reviewed</dt><dd>{dateLabel(provider.last_reviewed_on)}</dd></div><div><dt>Next review</dt><dd className={provider.review_due ? "is-alert" : ""}>{dateLabel(provider.next_review_due_on)}</dd></div><div><dt>Interval</dt><dd>{provider.review_interval_days ? `${provider.review_interval_days} days` : "Not set"}</dd></div></dl></section>
          <section className="qms-provider-detail-section"><div className="qms-provider-section-heading"><div><span className="qms-provider-eyebrow">Current controls</span><h3>Attention required</h3></div></div><div className="qms-provider-health-list"><span className={provider.review_due ? "is-alert" : "is-ok"}>{provider.review_due ? <AlertTriangle size={17} /> : <CheckCircle2 size={17} />}{provider.review_due ? "Provider review is due" : "Review date is current"}</span><span className={approvalBlocked ? "is-alert" : "is-ok"}>{approvalBlocked ? <Ban size={17} /> : <ShieldCheck size={17} />}{approvalBlocked ? "Required contract is missing" : "Contract gate satisfied"}</span></div></section>
        </div>
      )}
    </div>
  );
}

const providerRecordViews:Record<string,string>={evaluations:"Provider evaluations","supplier-audits":"Provider audits","supplier-findings":"Provider findings"};
export default function QmsExternalProvidersPage(): React.ReactElement {
  const {amoCode=""}=useParams<{amoCode:string}>();
  const location=useLocation();
  const view=location.pathname.split("/").filter(Boolean).at(-1)||"register";
  if(providerRecordViews[view]) return <DepartmentLayout amoCode={amoCode} activeDepartment="quality"><div className="qms-provider-page qms-surface-root"><header className="qms-provider-page__header"><h1>{providerRecordViews[view]}</h1><Link className="qms-provider-button is-secondary" to={`/maintenance/${encodeURIComponent(amoCode)}/quality/suppliers/register`}>External Providers</Link></header><QmsRegisterPage embedded/></div></DepartmentLayout>;
  return <ProviderWorkspace key={`${amoCode}:${view}`}/>;
}

function ProviderWorkspace(): React.ReactElement {
  const { amoCode = "" } = useParams<{ amoCode: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const agreementWorkspace = /\/suppliers\/agreements\/?$/i.test(location.pathname);
  const detailMatch = location.pathname.match(/\/suppliers\/(\d+)(?:\/(overview|approval|contracts|evidence|monitoring|qualification))?\/?$/i);
  const detailId = detailMatch ? Number(detailMatch[1]) : null;
  const detailTab = (detailMatch?.[2]?.toLowerCase() || "overview") as DetailTab;
  const [summary, setSummary] = useState<ProviderGovernanceSummary | null>(null);
  const [items, setItems] = useState<ProviderListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const pageSize = 50;
  const [search, setSearch] = useState("");
  const fixedStatus=location.pathname.endsWith("/approved-list")?"APPROVED":location.pathname.endsWith("/expired-approvals")?"EXPIRED":"";
  const [statusFilter, setStatusFilter] = useState(fixedStatus);
  const [kindFilter, setKindFilter] = useState("");
  const [riskFilter, setRiskFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  // A changed tenant, filter, or page must invalidate an older response,
  // even while the next debounced request has not started.
  const latestListRequest = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++latestListRequest.current;
    if (!amoCode || detailId || agreementWorkspace) return;
    setLoading(true);
    setError(null);
    try {
      const [nextSummary, providers] = await Promise.all([
        getProviderGovernanceSummary(amoCode),
        getExternalProviders(amoCode, { search, status: statusFilter, providerKind: kindFilter, riskLevel: riskFilter, limit: pageSize, offset: page * pageSize }),
      ]);
      if (requestId !== latestListRequest.current) return;
      setSummary(nextSummary);
      setItems(providers.items);
      setTotal(providers.total);
    } catch (err) {
      if (requestId === latestListRequest.current) setError(errorMessage(err));
    } finally {
      if (requestId === latestListRequest.current) setLoading(false);
    }
  }, [amoCode, detailId, agreementWorkspace, kindFilter, riskFilter, search, statusFilter, page]);

  useEffect(() => {
    const requestSequence = latestListRequest;
    const timer = window.setTimeout(() => { void load(); }, search ? 220 : 0);
    return () => {
      window.clearTimeout(timer);
      ++requestSequence.current;
    };
  }, [load, search]);

  const basePath = useMemo(() => `/maintenance/${encodeURIComponent(amoCode)}/quality/suppliers`, [amoCode]);

  if (agreementWorkspace) {
    return <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
      <ProviderAgreementsWorkspace amoCode={amoCode} onBack={() => navigate(`${basePath}/register`)} />
    </DepartmentLayout>;
  }

  if (detailId) {
    return (
      <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
        <ProviderDetailWorkspace amoCode={amoCode} providerId={detailId} tab={detailTab} onBack={() => navigate(`${basePath}/register`)} />
      </DepartmentLayout>
    );
  }

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
    <main className="qms-provider-page qms-surface-root">
      <header className="qms-provider-page__header">
        <div>
          <h1>{fixedStatus==="APPROVED"?"Approved external providers":fixedStatus==="EXPIRED"?"Expired provider approvals":"External Providers"}</h1>
        </div>
        <div className="qms-provider-page__actions">
          <a className="qms-provider-button is-secondary" href={`/vendor/login?amo=${encodeURIComponent(amoCode)}`} target="_blank" rel="noreferrer">Vendor sign in</a>
          <button className="qms-provider-button is-secondary" onClick={() => void load()} disabled={loading}><RefreshCw size={16} />Refresh</button>
          {(isTenantAdmin(getCachedUser()) || getCachedUser()?.role === "QUALITY_MANAGER") && <button className="qms-provider-button" onClick={() => setCreating(true)}><Plus size={16} />Add provider</button>}
        </div>
      </header>

      {summary && (
        <section className="qms-provider-summary" aria-label="Provider governance summary">
          <SummaryCard icon={Building2} label="Active providers" value={summary.total} />
          <SummaryCard icon={ShieldCheck} label="Approved" value={summary.approved} />
          <SummaryCard icon={ShieldAlert} label="Suspended" value={summary.suspended} alert />
          <SummaryCard icon={CalendarClock} label="Reviews due" value={summary.review_due} alert />
          <SummaryCard icon={FileText} label="Contract gaps" value={summary.required_contract_missing} alert />
          <SummaryCard icon={FileCheck2} label="Evidence expiring" value={summary.evidence_expiring} alert />
        </section>
      )}

      <ProviderPortfolio amoCode={amoCode} />
      <ProviderAlertSettingsPanel amoCode={amoCode} department="QUALITY" />
      {creating && <ProviderCreatePanel amoCode={amoCode} onClose={() => setCreating(false)} onCreated={(provider) => navigate(`${basePath}/${provider.id}/overview`)} />}
      {error && <div className="qms-provider-alert is-error"><AlertTriangle size={17} />{error}</div>}

      <section className="qms-provider-register">
        <div className="qms-provider-toolbar">
          <label className="qms-provider-search"><Search size={17} /><input aria-label="Search external providers" placeholder="Search code, legal name or trading name" value={search} onChange={(e) => {setSearch(e.target.value);setPage(0);}} /></label>
          <select aria-label="Provider status" disabled={Boolean(fixedStatus)} value={statusFilter} onChange={(e) => {setStatusFilter(e.target.value);setPage(0);}}><option value="">All statuses</option>{PROVIDER_STATUSES.map((item) => <option key={item} value={item}>{titleCase(item)}</option>)}</select>
          <select aria-label="Provider type" value={kindFilter} onChange={(e) => {setKindFilter(e.target.value);setPage(0);}}><option value="">All provider types</option>{PROVIDER_KINDS.map((item) => <option key={item} value={item}>{titleCase(item)}</option>)}</select>
          <select aria-label="Provider risk" value={riskFilter} onChange={(e) => {setRiskFilter(e.target.value);setPage(0);}}><option value="">All risk levels</option>{PROVIDER_RISKS.map((item) => <option key={item}>{item}</option>)}</select>
        </div>
        {loading ? <div className="qms-provider-loading"><RefreshCw className="is-spinning" size={20} />Loading provider governance…</div> : (
          <div className="qms-provider-table-wrap">
            <table className="qms-provider-table">
              <thead><tr><th>Provider</th><th>Type</th><th>Status</th><th>Risk</th><th>Scope</th><th>Contract</th><th>Evidence</th><th>Review</th><th aria-label="Open" /></tr></thead>
              <tbody>
                {items.map((provider) => (
                  <tr key={provider.id} onClick={() => navigate(`${basePath}/${provider.id}/overview`)}>
                    <td><strong>{provider.legal_name}</strong><span>{provider.supplier_code}{provider.trading_name ? ` · ${provider.trading_name}` : ""}</span></td>
                    <td>{titleCase(provider.provider_kind)}</td>
                    <td><StatusPill value={provider.status} /></td>
                    <td><span className={`qms-provider-risk is-${provider.risk_level.toLowerCase()}`}>{provider.risk_level}</span></td>
                    <td>{provider.active_scope_count || "—"}</td>
                    <td className={provider.contract_gap ? "is-attention" : ""}>{provider.contract_gap ? "Missing" : provider.active_contract_count || "—"}</td>
                    <td>{provider.verified_evidence_count || "—"}</td>
                    <td className={provider.review_due ? "is-attention" : ""}>{provider.review_due ? "Due" : dateLabel(provider.next_review_due_on)}</td>
                    <td><ChevronRight size={17} /></td>
                  </tr>
                ))}
                {items.length === 0 && <tr><td colSpan={9}><div className="qms-provider-empty">No external providers match the current filters.</div></td></tr>}
              </tbody>
            </table>
            <nav aria-label="Provider register pages" style={{display:"flex",gap:12,alignItems:"center",padding:12}}>
              <button type="button" disabled={loading||page===0} onClick={()=>setPage(x=>x-1)}>Previous</button>
              <span>Showing {items.length ? page*pageSize+1 : 0}–{page*pageSize+items.length} of {total} governed providers</span>
              <button type="button" disabled={loading||(page+1)*pageSize>=total} onClick={()=>setPage(x=>x+1)}>Next</button>
            </nav>
          </div>
        )}
      </section>
    </main>
    </DepartmentLayout>
  );
}
