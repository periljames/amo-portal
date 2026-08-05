import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  BadgeCheck,
  BriefcaseBusiness,
  CalendarClock,
  FileBadge2,
  IdCard,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
  UserRoundCheck,
} from "lucide-react";
import {
  createPersonnelCredential,
  getUserGovernance,
  saveComplianceProfile,
  type ComplianceProfile,
  type UserGovernance,
} from "../../services/corporateStructure";
import "../../styles/admin-corporate-structure.css";
import "../../styles/admin-user-governance.css";

const today = new Date().toISOString().slice(0, 10);

function message(error: unknown): string {
  return error instanceof Error ? error.message : "The personnel governance record could not be loaded.";
}

function emptyProfile(userName = ""): Record<string, string | boolean> {
  return {
    legal_name: userName,
    preferred_name: "",
    nationality: "",
    residence_country: "",
    identity_verified: false,
    identity_reference: "",
    emergency_contact_name: "",
    emergency_contact_relationship: "",
    emergency_contact_phone: "",
    data_classification: "CONFIDENTIAL",
    retention_class: "PERSONNEL_ACTIVE_PLUS_RETENTION",
    confidentiality_ack_at: "",
    code_of_conduct_ack_at: "",
    conflict_declaration_at: "",
    competence_status: "NOT_ASSESSED",
    training_status: "NOT_ASSESSED",
    authorisation_status: "NOT_APPLICABLE",
    medical_fitness_status: "NOT_APPLICABLE",
    last_competence_assessment_on: "",
    next_review_on: "",
    compliance_owner_user_id: "",
    restrictions: "",
    notes: "",
  };
}

function profileValues(profile: ComplianceProfile | null, userName: string): Record<string, string | boolean> {
  if (!profile) return emptyProfile(userName);
  return {
    legal_name: profile.legal_name ?? userName,
    preferred_name: profile.preferred_name ?? "",
    nationality: profile.nationality ?? "",
    residence_country: profile.residence_country ?? "",
    identity_verified: profile.identity_verified,
    identity_reference: profile.identity_reference ?? "",
    emergency_contact_name: profile.emergency_contact_name ?? "",
    emergency_contact_relationship: profile.emergency_contact_relationship ?? "",
    emergency_contact_phone: profile.emergency_contact_phone ?? "",
    data_classification: profile.data_classification,
    retention_class: profile.retention_class,
    confidentiality_ack_at: profile.confidentiality_ack_at?.slice(0, 16) ?? "",
    code_of_conduct_ack_at: profile.code_of_conduct_ack_at?.slice(0, 16) ?? "",
    conflict_declaration_at: profile.conflict_declaration_at?.slice(0, 16) ?? "",
    competence_status: profile.competence_status,
    training_status: profile.training_status,
    authorisation_status: profile.authorisation_status,
    medical_fitness_status: profile.medical_fitness_status,
    last_competence_assessment_on: profile.last_competence_assessment_on ?? "",
    next_review_on: profile.next_review_on ?? "",
    compliance_owner_user_id: profile.compliance_owner_user_id ?? "",
    restrictions: profile.restrictions ?? "",
    notes: profile.notes ?? "",
  };
}

export default function UserGovernancePage() {
  const { id = "" } = useParams();
  const [data, setData] = useState<UserGovernance | null>(null);
  const [profile, setProfile] = useState<Record<string, string | boolean>>(emptyProfile());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [credentialOpen, setCredentialOpen] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const result = await getUserGovernance(id);
      setData(result);
      setProfile(profileValues(result.compliance_profile, result.user.full_name));
    } catch (loadError) {
      setError(message(loadError));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { void load(); }, [load]);

  const completion = useMemo(() => {
    if (!data) return [];
    return [
      [Boolean(data.primary_assignment), "Primary position"],
      [Boolean(data.active_engagement), "Engagement terms"],
      [Boolean(data.compliance_profile?.identity_verified), "Verified identity"],
      [["CURRENT", "VALID"].includes(data.compliance_profile?.competence_status ?? ""), "Competence current"],
      [["CURRENT", "VALID"].includes(data.compliance_profile?.training_status ?? ""), "Training current"],
      [Boolean(data.compliance_profile?.code_of_conduct_ack_at), "Conduct acknowledged"],
    ] as Array<[boolean, string]>;
  }, [data]);

  const value = (key: string) => String(profile[key] ?? "");
  const checked = (key: string) => Boolean(profile[key]);
  const set = (key: string, next: string | boolean) => setProfile((current) => ({ ...current, [key]: next }));

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    if (!id) return;
    setSaving(true);
    setError(null);
    const payload = Object.fromEntries(Object.entries(profile).map(([key, raw]) => {
      if (typeof raw === "boolean") return [key, raw];
      return [key, raw.trim() || null];
    }));
    try {
      await saveComplianceProfile(id, payload);
      await load();
    } catch (saveError) {
      setError(message(saveError));
    } finally {
      setSaving(false);
    }
  }

  if (loading && !data) return <main className="corp-page user-governance"><div className="governance-loading"><RefreshCw className="spin" size={20}/> Loading personnel governance profile…</div></main>;
  if (!data) return <main className="corp-page user-governance"><Link className="corp-row-link" to="/admin/users"><ArrowLeft size={15}/> Back to users</Link><div className="corp-alert"><AlertTriangle size={17}/>{error ?? "Personnel record not found."}</div></main>;

  return (
    <main className="corp-page user-governance">
      <header className="corp-page__header governance-header">
        <div>
          <Link className="governance-back" to="/admin/organization"><ArrowLeft size={15}/> Corporate structure</Link>
          <span className="corp-eyebrow"><UserRoundCheck size={15}/> Personnel master profile</span>
          <h1>{data.user.full_name}</h1>
          <p>{data.user.staff_code} · {data.user.email} · {data.user.position_title ?? "Position not assigned"}</p>
        </div>
        <div className="governance-score" aria-label={`Personnel readiness ${data.readiness_score} percent`}>
          <strong>{data.readiness_score}%</strong><span>readiness</span>
        </div>
      </header>

      {error ? <div className="corp-alert"><AlertTriangle size={17}/><span>{error}</span></div> : null}

      <section className="governance-summary">
        <article><BriefcaseBusiness size={18}/><span><small>Primary assignment</small><strong>{data.primary_assignment?.position_title ?? "Not assigned"}</strong><em>{data.primary_assignment?.unit_name ?? "Corporate placement required"}</em></span></article>
        <article><CalendarClock size={18}/><span><small>Engagement</small><strong>{data.active_engagement?.engagement_type ?? "Not recorded"}</strong><em>{data.active_engagement?.end_date ? `Ends ${data.active_engagement.end_date}` : data.active_engagement ? "Open ended" : "Terms required"}</em></span></article>
        <article><ShieldCheck size={18}/><span><small>Competence / training</small><strong>{data.compliance_profile?.competence_status ?? "NOT_ASSESSED"}</strong><em>{data.compliance_profile?.training_status ?? "NOT_ASSESSED"}</em></span></article>
        <article><FileBadge2 size={18}/><span><small>Credentials</small><strong>{data.credentials.length}</strong><em>{data.credentials.filter((item) => item.expires_on && item.expires_on <= new Date(Date.now() + 90 * 86400000).toISOString().slice(0, 10)).length} due within 90 days</em></span></article>
      </section>

      <div className="governance-layout">
        <section className="governance-main">
          <form className="corp-panel governance-form" onSubmit={(event) => void saveProfile(event)}>
            <header><div><h2>Identity and governance profile</h2><p>Store only the minimum controlled personnel data required for employment, competence and accountability evidence.</p></div><button className="corp-button" type="submit" disabled={saving}><Save size={15}/>{saving ? "Saving…" : "Save profile"}</button></header>
            <div className="governance-section">
              <h3><IdCard size={16}/> Identity</h3>
              <div className="governance-fields governance-fields--3"><Field label="Legal name"><input value={value("legal_name")} onChange={(e)=>set("legal_name",e.target.value)} /></Field><Field label="Preferred name"><input value={value("preferred_name")} onChange={(e)=>set("preferred_name",e.target.value)} /></Field><Field label="Nationality"><input value={value("nationality")} onChange={(e)=>set("nationality",e.target.value)} /></Field><Field label="Residence country"><input value={value("residence_country")} onChange={(e)=>set("residence_country",e.target.value)} /></Field><Field label="Identity evidence reference"><input value={value("identity_reference")} onChange={(e)=>set("identity_reference",e.target.value)} /></Field><label className="corp-check governance-check"><input type="checkbox" checked={checked("identity_verified")} onChange={(e)=>set("identity_verified",e.target.checked)} /><span>Identity evidence verified</span></label></div>
            </div>
            <div className="governance-section">
              <h3><BadgeCheck size={16}/> Competence and fitness status</h3>
              <div className="governance-fields governance-fields--4"><StatusSelect label="Competence" value={value("competence_status")} onChange={(next)=>set("competence_status",next)} options={["NOT_ASSESSED","CURRENT","DUE","RESTRICTED","EXPIRED"]}/><StatusSelect label="Training" value={value("training_status")} onChange={(next)=>set("training_status",next)} options={["NOT_ASSESSED","CURRENT","DUE","INCOMPLETE","EXPIRED"]}/><StatusSelect label="Authorisation" value={value("authorisation_status")} onChange={(next)=>set("authorisation_status",next)} options={["NOT_APPLICABLE","CURRENT","PENDING","SUSPENDED","REVOKED","EXPIRED"]}/><StatusSelect label="Medical fitness" value={value("medical_fitness_status")} onChange={(next)=>set("medical_fitness_status",next)} options={["NOT_APPLICABLE","CURRENT","RESTRICTED","DUE","EXPIRED"]}/><Field label="Last competence assessment"><input type="date" value={value("last_competence_assessment_on")} onChange={(e)=>set("last_competence_assessment_on",e.target.value)} /></Field><Field label="Next profile review"><input type="date" value={value("next_review_on")} onChange={(e)=>set("next_review_on",e.target.value)} /></Field></div>
            </div>
            <div className="governance-section">
              <h3><ShieldCheck size={16}/> Ethics, privacy and retention</h3>
              <div className="governance-fields governance-fields--3"><Field label="Data classification"><select value={value("data_classification")} onChange={(e)=>set("data_classification",e.target.value)}><option>CONFIDENTIAL</option><option>RESTRICTED</option><option>INTERNAL</option></select></Field><Field label="Retention class"><select value={value("retention_class")} onChange={(e)=>set("retention_class",e.target.value)}><option>PERSONNEL_ACTIVE_PLUS_RETENTION</option><option>REGULATORY_PERSONNEL_RECORD</option><option>CONTINGENT_WORKER_RECORD</option></select></Field><Field label="Confidentiality acknowledgement"><input type="datetime-local" value={value("confidentiality_ack_at")} onChange={(e)=>set("confidentiality_ack_at",e.target.value)} /></Field><Field label="Code of conduct acknowledgement"><input type="datetime-local" value={value("code_of_conduct_ack_at")} onChange={(e)=>set("code_of_conduct_ack_at",e.target.value)} /></Field><Field label="Conflict declaration"><input type="datetime-local" value={value("conflict_declaration_at")} onChange={(e)=>set("conflict_declaration_at",e.target.value)} /></Field></div>
            </div>
            <div className="governance-section">
              <h3><UserRoundCheck size={16}/> Emergency contact</h3>
              <div className="governance-fields governance-fields--3"><Field label="Contact name"><input value={value("emergency_contact_name")} onChange={(e)=>set("emergency_contact_name",e.target.value)} /></Field><Field label="Relationship"><input value={value("emergency_contact_relationship")} onChange={(e)=>set("emergency_contact_relationship",e.target.value)} /></Field><Field label="Telephone"><input value={value("emergency_contact_phone")} onChange={(e)=>set("emergency_contact_phone",e.target.value)} /></Field></div>
            </div>
            <div className="governance-section"><h3>Restrictions and controlled notes</h3><div className="governance-fields"><Field label="Restrictions"><textarea rows={3} value={value("restrictions")} onChange={(e)=>set("restrictions",e.target.value)} /></Field><Field label="Governance notes"><textarea rows={3} value={value("notes")} onChange={(e)=>set("notes",e.target.value)} /></Field></div></div>
          </form>

          <section className="corp-panel governance-records">
            <header><div><h2>Credentials and evidence</h2><p>Licences, authorisations, competence assessments, training and medical-status evidence.</p></div><button className="corp-button" type="button" onClick={()=>setCredentialOpen((open)=>!open)}><Plus size={15}/> Add credential</button></header>
            {credentialOpen ? <CredentialForm userId={id} onSaved={async()=>{ setCredentialOpen(false); await load(); }} onError={setError} /> : null}
            <div className="corp-table-shell governance-table"><table className="corp-table"><thead><tr><th>Credential</th><th>Authority / reference</th><th>Issue / expiry</th><th>Status</th><th>Restrictions</th></tr></thead><tbody>{data.credentials.map((item)=><tr key={item.id}><td><strong>{item.title ?? item.credential_type}</strong><small>{item.credential_type}</small></td><td><strong>{item.authority ?? "Internal"}</strong><small>{item.reference}</small></td><td><strong>{item.issued_on ?? "—"}</strong><small>{item.expires_on ? `Expires ${item.expires_on}` : "No expiry"}</small></td><td><span className={`corp-status corp-status--${item.status === "VALID" ? "good" : item.status === "EXPIRING" ? "warn" : "bad"}`}>{item.status}</span></td><td>{item.restrictions ?? "—"}</td></tr>)}</tbody></table>{!data.credentials.length ? <div className="governance-no-records">No credential evidence has been registered.</div> : null}</div>
          </section>
        </section>

        <aside className="governance-aside">
          <section className="corp-panel"><header><div><h2>Readiness checks</h2><p>Account access is not evidence of appointment or competence.</p></div></header><ul className="governance-checklist">{completion.map(([complete,label])=><li key={label} className={complete ? "is-complete" : "is-gap"}><span>{complete ? "✓" : "!"}</span><strong>{label}</strong></li>)}</ul></section>
          {data.readiness_gaps.length ? <section className="corp-panel governance-gaps"><header><div><h2>Open gaps</h2><p>Resolve before relying on the user for controlled responsibilities.</p></div></header><ul>{data.readiness_gaps.map((gap)=><li key={gap}><AlertTriangle size={15}/>{gap}</li>)}</ul></section> : null}
          <section className="corp-panel governance-history"><header><div><h2>Assignment history</h2><p>Effective-dated corporate appointments.</p></div></header>{data.assignments.map((item)=><article key={item.id}><strong>{item.position_title}</strong><span>{item.unit_name}</span><small>{item.assignment_type} · {item.effective_from} {item.effective_to ? `to ${item.effective_to}` : "onwards"}</small></article>)}</section>
          <section className="corp-panel governance-history"><header><div><h2>Engagement history</h2><p>Employment and contingent workforce terms.</p></div></header>{data.engagements.map((item)=><article key={item.id}><strong>{item.engagement_type}</strong><span>{item.contract_reference ?? item.status}</span><small>{item.start_date} {item.end_date ? `to ${item.end_date}` : "onwards"}</small></article>)}</section>
        </aside>
      </div>
    </main>
  );
}

function CredentialForm({ userId, onSaved, onError }: { userId: string; onSaved: () => Promise<void>; onError: (value: string) => void }) {
  const [saving, setSaving] = useState(false);
  const [values, setValues] = useState({ credential_type: "LICENCE", authority: "", reference: "", title: "", issued_on: "", expires_on: "", status: "VALID", restrictions: "" });
  const set = (key: keyof typeof values, value: string) => setValues((current)=>({...current,[key]:value}));
  async function submit(event: FormEvent) { event.preventDefault(); setSaving(true); try { await createPersonnelCredential({ user_id:userId, ...values, authority:values.authority||null, title:values.title||null, issued_on:values.issued_on||null, expires_on:values.expires_on||null, restrictions:values.restrictions||null, scope:{} }); await onSaved(); } catch (error) { onError(message(error)); } finally { setSaving(false); } }
  return <form className="governance-credential-form" onSubmit={(event)=>void submit(event)}><div className="governance-fields governance-fields--4"><Field label="Type"><select value={values.credential_type} onChange={(e)=>set("credential_type",e.target.value)}><option>LICENCE</option><option>AUTHORISATION</option><option>COMPETENCE</option><option>TRAINING</option><option>MEDICAL</option><option>CERTIFICATE</option></select></Field><Field label="Authority"><input value={values.authority} onChange={(e)=>set("authority",e.target.value)} /></Field><Field label="Reference"><input required value={values.reference} onChange={(e)=>set("reference",e.target.value)} /></Field><Field label="Title"><input value={values.title} onChange={(e)=>set("title",e.target.value)} /></Field><Field label="Issued on"><input type="date" value={values.issued_on} onChange={(e)=>set("issued_on",e.target.value)} /></Field><Field label="Expires on"><input type="date" min={values.issued_on || today} value={values.expires_on} onChange={(e)=>set("expires_on",e.target.value)} /></Field><Field label="Status"><select value={values.status} onChange={(e)=>set("status",e.target.value)}><option>VALID</option><option>PENDING</option><option>RESTRICTED</option><option>SUSPENDED</option><option>EXPIRED</option></select></Field><Field label="Restrictions"><input value={values.restrictions} onChange={(e)=>set("restrictions",e.target.value)} /></Field></div><button className="corp-button" type="submit" disabled={saving}>{saving ? "Saving…" : "Register evidence"}</button></form>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="corp-field"><span>{label}</span>{children}</label>; }
function StatusSelect({ label, value, options, onChange }: { label:string; value:string; options:string[]; onChange:(value:string)=>void }) { return <Field label={label}><select value={value} onChange={(e)=>onChange(e.target.value)}>{options.map((item)=><option key={item}>{item}</option>)}</select></Field>; }
