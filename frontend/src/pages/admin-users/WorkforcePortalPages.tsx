import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowLeft, BriefcaseBusiness, CalendarClock, FileBadge2, RefreshCw, ShieldCheck, UserRoundCheck, UsersRound } from "lucide-react";
import {
  getMyOrganizationProfile,
  getMyTeam,
  type ComplianceProfile,
  type ManagerTeamMember,
  type PersonnelCredential,
  type PositionAssignment,
  type WorkforceEngagement,
} from "../../services/corporateStructure";
import "../../styles/admin-corporate-structure.css";
import "../../styles/workforce-portals.css";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The workforce portal could not be loaded.";
}

export function ManagerTeamPage() {
  const [team, setTeam] = useState<ManagerTeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setTeam(await getMyTeam()); } catch (loadError) { setError(errorMessage(loadError)); } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const gaps = team.filter((member) => member.readiness_score < 100).length;
  const expiring = team.reduce((sum, member) => sum + member.expiring_credentials, 0);

  return <main className="corp-page workforce-portal">
    <header className="corp-page__header"><div><Link className="workforce-back" to="/"><ArrowLeft size={15}/> Portal home</Link><span className="corp-eyebrow"><UsersRound size={15}/> Manager workspace</span><h1>My team</h1><p>Direct reports, corporate placement and personnel readiness. This view does not grant HR, quality or authorisation approval rights.</p></div><button className="corp-icon-button" type="button" onClick={()=>void load()} disabled={loading}><RefreshCw size={17}/></button></header>
    {error ? <div className="corp-alert"><AlertTriangle size={17}/>{error}</div> : null}
    <section className="workforce-metrics"><article><strong>{team.length}</strong><span>direct reports</span></article><article className={gaps ? "is-risk" : ""}><strong>{gaps}</strong><span>readiness gaps</span></article><article className={expiring ? "is-risk" : ""}><strong>{expiring}</strong><span>credentials due ≤ 90 days</span></article><article><strong>{team.filter((item)=>item.engagement_type && item.engagement_type !== "EMPLOYEE").length}</strong><span>contingent workers</span></article></section>
    <section className="corp-table-shell workforce-table"><table className="corp-table"><thead><tr><th>Person</th><th>Position / unit</th><th>Engagement</th><th>Competence</th><th>Training</th><th>Evidence due</th><th>Readiness</th></tr></thead><tbody>{team.map((member)=><tr key={member.user_id}><td><strong>{member.full_name}</strong><small>{member.staff_code} · {member.email}</small></td><td><strong>{member.position_title}</strong><small>{member.unit_name}</small></td><td><strong>{member.engagement_type ?? "Not recorded"}</strong><small>{member.engagement_end_date ? `Ends ${member.engagement_end_date}` : ""}</small></td><td><span className={`corp-status corp-status--${["CURRENT","VALID"].includes(member.competence_status) ? "good" : "warn"}`}>{member.competence_status}</span></td><td><span className={`corp-status corp-status--${["CURRENT","VALID"].includes(member.training_status) ? "good" : "warn"}`}>{member.training_status}</span></td><td>{member.expiring_credentials}</td><td><strong>{member.readiness_score}%</strong><small title={member.readiness_gaps.join("; ")}>{member.readiness_gaps[0] ?? "Ready"}</small></td></tr>)}</tbody></table>{!team.length && !loading ? <div className="workforce-empty"><UsersRound size={26}/><strong>No direct reports</strong><span>Your current primary assignment has no active personnel reporting to you.</span></div> : null}</section>
  </main>;
}

type MyProfile = {
  user: { id: string; full_name: string; staff_code: string; email: string; position_title: string | null; role: string };
  assignment: PositionAssignment | null;
  engagement: WorkforceEngagement | null;
  compliance_profile: ComplianceProfile | null;
  credentials: PersonnelCredential[];
};

export function MyOrganizationProfilePage() {
  const [profile, setProfile] = useState<MyProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { void getMyOrganizationProfile().then(setProfile).catch((loadError)=>setError(errorMessage(loadError))); }, []);
  if (error) return <main className="corp-page workforce-portal"><div className="corp-alert"><AlertTriangle size={17}/>{error}</div></main>;
  if (!profile) return <main className="corp-page workforce-portal"><div className="workforce-empty"><RefreshCw size={21}/><strong>Loading profile…</strong></div></main>;
  return <main className="corp-page workforce-portal">
    <header className="corp-page__header"><div><Link className="workforce-back" to="/"><ArrowLeft size={15}/> Portal home</Link><span className="corp-eyebrow"><UserRoundCheck size={15}/> Self-service record</span><h1>{profile.user.full_name}</h1><p>{profile.user.staff_code} · {profile.user.email}. Contact your manager or administrator to correct controlled corporate, competence or access records.</p></div></header>
    <section className="workforce-profile-grid">
      <article className="corp-panel"><header><div><h2><BriefcaseBusiness size={16}/> Corporate assignment</h2></div></header><dl><dt>Position</dt><dd>{profile.assignment?.position_title ?? "Not assigned"}</dd><dt>Organization unit</dt><dd>{profile.assignment?.unit_name ?? "Not assigned"}</dd><dt>Reporting manager</dt><dd>{profile.assignment?.reporting_manager_name ?? "Not assigned"}</dd><dt>Assignment type</dt><dd>{profile.assignment?.assignment_type ?? "—"}</dd><dt>Effective</dt><dd>{profile.assignment ? `${profile.assignment.effective_from}${profile.assignment.effective_to ? ` to ${profile.assignment.effective_to}` : " onwards"}` : "—"}</dd></dl></article>
      <article className="corp-panel"><header><div><h2><CalendarClock size={16}/> Engagement terms</h2></div></header><dl><dt>Type</dt><dd>{profile.engagement?.engagement_type ?? "Not recorded"}</dd><dt>Period</dt><dd>{profile.engagement ? `${profile.engagement.start_date}${profile.engagement.end_date ? ` to ${profile.engagement.end_date}` : " onwards"}` : "—"}</dd><dt>Sponsor</dt><dd>{profile.engagement?.sponsor_name ?? "Not applicable"}</dd><dt>Access expiry</dt><dd>{profile.engagement?.access_expiry_on ?? "No automatic expiry recorded"}</dd></dl></article>
      <article className="corp-panel"><header><div><h2><ShieldCheck size={16}/> Compliance status</h2></div></header><dl><dt>Identity</dt><dd>{profile.compliance_profile?.identity_verified ? "Verified" : "Not verified"}</dd><dt>Competence</dt><dd>{profile.compliance_profile?.competence_status ?? "NOT_ASSESSED"}</dd><dt>Training</dt><dd>{profile.compliance_profile?.training_status ?? "NOT_ASSESSED"}</dd><dt>Authorisation</dt><dd>{profile.compliance_profile?.authorisation_status ?? "NOT_APPLICABLE"}</dd><dt>Next review</dt><dd>{profile.compliance_profile?.next_review_on ?? "Not scheduled"}</dd></dl></article>
      <article className="corp-panel workforce-credentials"><header><div><h2><FileBadge2 size={16}/> Credentials</h2></div></header>{profile.credentials.map((item)=><div key={item.id}><strong>{item.title ?? item.credential_type}</strong><span>{item.authority ?? "Internal"} · {item.reference}</span><small>{item.expires_on ? `Expires ${item.expires_on}` : "No expiry"} · {item.status}</small></div>)}{!profile.credentials.length ? <p>No credentials are visible in the governance register.</p> : null}</article>
    </section>
  </main>;
}
