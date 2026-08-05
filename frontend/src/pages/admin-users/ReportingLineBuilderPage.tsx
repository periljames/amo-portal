import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  BadgeCheck,
  BriefcaseBusiness,
  ChevronRight,
  GitBranch,
  Network,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
  UserPlus,
  X,
} from "lucide-react";
import {
  createGuidedAssignment,
  createReportingChain,
  decideTitlePreference,
  getReportingWorkspace,
  updateReportingPosition,
  type ChainRoleInput,
  type GuidedAssignmentInput,
  type ReportingPosition,
  type ReportingWorkspace,
} from "../../services/reportingLines";
import "../../styles/admin-corporate-structure.css";
import "../../styles/reporting-line-builder.css";

type PanelMode = "chain" | "assignment" | "edit" | null;
type ChainDraft = { title: string; code: string; headcount: string; supervisory: boolean };

const today = new Date().toISOString().slice(0, 10);

function message(error: unknown): string {
  return error instanceof Error ? error.message : "The reporting-line operation could not be completed.";
}

function directManager(position: ReportingPosition | undefined) {
  const direct = position?.manager_candidates.filter((item) => item.relationship === "DIRECT_PARENT") ?? [];
  return direct.length === 1 ? direct[0] : null;
}

function canEditPosition(workspace: ReportingWorkspace, position: ReportingPosition): boolean {
  if (!position.editable) return false;
  return workspace.actor_mode === "ADMIN" || (!position.is_regulatory_post && !position.authority_acceptance_required);
}

export default function ReportingLineBuilderPage() {
  const [workspace, setWorkspace] = useState<ReportingWorkspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [panel, setPanel] = useState<PanelMode>(null);
  const [selectedPositionId, setSelectedPositionId] = useState("");
  const [unitFilter, setUnitFilter] = useState("");
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setWorkspace(await getReportingWorkspace());
    } catch (loadError) {
      setError(message(loadError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const editableUnits = useMemo(() => workspace?.units.filter((unit) => unit.editable) ?? [], [workspace]);
  const editablePositions = useMemo(
    () => workspace?.positions.filter((position) => canEditPosition(workspace, position)) ?? [],
    [workspace],
  );
  const visiblePositions = useMemo(() => {
    if (!workspace) return [];
    const term = search.trim().toLowerCase();
    return workspace.positions.filter((position) => {
      if (unitFilter && position.unit_id !== unitFilter) return false;
      if (!term) return true;
      return [
        position.canonical_title,
        position.code,
        position.unit_name,
        position.reports_to_title ?? "",
        ...position.occupants.flatMap((item) => [item.user_name, item.display_title]),
      ].some((value) => value.toLowerCase().includes(term));
    });
  }, [search, unitFilter, workspace]);

  async function run(action: () => Promise<unknown>) {
    setSaving(true);
    setError(null);
    try {
      await action();
      setPanel(null);
      setSelectedPositionId("");
      await load();
    } catch (saveError) {
      setError(message(saveError));
    } finally {
      setSaving(false);
    }
  }

  const occupied = workspace?.positions.reduce((sum, item) => sum + item.occupied_count, 0) ?? 0;
  const vacancies = workspace?.positions.reduce((sum, item) => sum + item.vacancy_count, 0) ?? 0;
  const selectedPosition = workspace?.positions.find((item) => item.id === selectedPositionId);

  return <main className="corp-page reporting-builder">
    <header className="corp-page__header reporting-builder__header"><div><Link className="workforce-back" to="/manager/team"><ArrowLeft size={15}/> My team</Link><span className="corp-eyebrow"><GitBranch size={15}/> Guided organization mapping</span><h1>Reporting lines</h1><p>Create any number of levels, assign people and keep preferred display titles separate from controlled positions and aviation authority.</p></div><div className="corp-header-actions">{workspace?.actor_mode === "ADMIN" ? <Link className="corp-button corp-button--quiet" to="/admin/organization"><Network size={16}/> Corporate structure</Link> : null}<button className="corp-icon-button" type="button" onClick={()=>void load()} disabled={loading} aria-label="Refresh reporting lines"><RefreshCw size={17}/></button></div></header>
    {error ? <div className="corp-alert" role="alert"><AlertTriangle size={17}/><span>{error}</span><button type="button" onClick={()=>setError(null)}><X size={15}/></button></div> : null}
    <section className="reporting-builder__boundary"><ShieldCheck size={18}/><div><strong>Authority remains independent</strong><span>{workspace?.authorization_boundary ?? "Loading control boundary…"}</span></div></section>
    <section className="reporting-builder__metrics"><article><strong>{editableUnits.length}</strong><span>manageable units</span></article><article><strong>{editablePositions.length}</strong><span>editable positions</span></article><article><strong>{occupied}</strong><span>active occupants</span></article><article className={vacancies ? "is-risk" : ""}><strong>{vacancies}</strong><span>open places</span></article><article className={workspace?.pending_title_preferences.length ? "is-risk" : ""}><strong>{workspace?.pending_title_preferences.length ?? 0}</strong><span>title requests</span></article></section>
    <section className="reporting-builder__toolbar"><div><select value={unitFilter} onChange={(event)=>setUnitFilter(event.target.value)} aria-label="Filter by organization unit"><option value="">All visible units</option>{workspace?.units.map((unit)=><option key={unit.id} value={unit.id}>{unit.name}</option>)}</select><input value={search} onChange={(event)=>setSearch(event.target.value)} placeholder="Search title, person or unit" aria-label="Search reporting lines"/></div><div><button className="corp-button corp-button--quiet" type="button" onClick={()=>{setSelectedPositionId("");setPanel("chain");}} disabled={!editableUnits.length}><Plus size={16}/> Add reporting levels</button><button className="corp-button" type="button" onClick={()=>{setSelectedPositionId("");setPanel("assignment");}} disabled={!editablePositions.length}><UserPlus size={16}/> Assign person</button></div></section>
    <div className={`reporting-builder__workspace${panel ? " is-split" : ""}`}>
      <section className="corp-table-shell reporting-builder__table" aria-busy={loading}><table className="corp-table"><thead><tr><th>Reporting hierarchy</th><th>Unit</th><th>Occupants and display titles</th><th>Manager mapping</th><th>Capacity</th><th></th></tr></thead><tbody>{visiblePositions.map((position)=>{
        const editable = workspace ? canEditPosition(workspace, position) : false;
        return <tr key={position.id}><td><div className="reporting-builder__position" style={{paddingInlineStart:`${Math.min(position.depth,8)*18}px`}}>{position.depth ? <ChevronRight size={14}/> : <GitBranch size={14}/>}<span><strong>{position.canonical_title}</strong><small>{position.code} · {position.reports_to_title ? `reports to ${position.reports_to_title}` : "top position"}</small></span></div></td><td><strong>{position.unit_name}</strong><small>{position.is_supervisory ? "Supervisory" : "Individual role"}</small></td><td>{position.occupants.length ? position.occupants.map((occupant)=><div className="reporting-builder__occupant" key={occupant.assignment_id}><strong>{occupant.user_name}</strong><span>{occupant.display_title}</span>{occupant.display_title !== occupant.canonical_title ? <small>Canonical: {occupant.canonical_title}</small> : <small>{occupant.staff_code}</small>}</div>) : <span className="reporting-builder__muted">Vacant</span>}</td><td>{position.occupants.length ? position.occupants.map((occupant)=><div key={occupant.assignment_id}><strong>{occupant.reporting_manager_name ?? "Not mapped"}</strong><small>{occupant.assignment_type}</small></div>) : <span className="reporting-builder__muted">Parent: {position.reports_to_title ?? "none"}</span>}</td><td><strong>{position.occupied_count} / {position.headcount_limit}</strong><small>{position.vacancy_count} open</small></td><td>{editable ? <button className="corp-row-link" type="button" onClick={()=>{setSelectedPositionId(position.id);setPanel("edit");}}>Edit <ChevronRight size={14}/></button> : <span className="corp-chip">View only</span>}</td></tr>;
      })}</tbody></table>{!visiblePositions.length && !loading ? <div className="corp-empty"><GitBranch size={26}/><strong>No reporting positions in view</strong><span>Add a chain such as Supervisor → Chief Crew → Engineer under the correct organization unit.</span></div> : null}</section>
      {panel === "chain" && workspace ? <ChainPanel workspace={workspace} saving={saving} initialParent={selectedPositionId} onClose={()=>setPanel(null)} onSubmit={(payload)=>run(()=>createReportingChain(workspace.actor_mode,payload))}/> : null}
      {panel === "assignment" && workspace ? <AssignmentPanel workspace={workspace} saving={saving} initialPosition={selectedPositionId} onClose={()=>setPanel(null)} onSubmit={(payload)=>run(()=>createGuidedAssignment(workspace.actor_mode,payload))}/> : null}
      {panel === "edit" && workspace && selectedPosition ? <EditPanel workspace={workspace} position={selectedPosition} saving={saving} onClose={()=>setPanel(null)} onSubmit={(payload)=>run(()=>updateReportingPosition(workspace.actor_mode,selectedPosition.id,payload))}/> : null}
    </div>
    <section className="corp-panel reporting-builder__requests"><header><div><h2><BadgeCheck size={17}/> Preferred title requests</h2><p>Approval changes only the displayed working title. The canonical position and every access or authorisation control remain unchanged.</p></div></header>{workspace?.pending_title_preferences.length ? <div className="reporting-builder__request-list">{workspace.pending_title_preferences.map((request)=><article key={request.id}><div><strong>{request.user_name}</strong><span>{request.canonical_title} → <b>{request.requested_title}</b></span><small>{request.reason || "No reason supplied"}</small></div><div><button className="corp-button corp-button--quiet" type="button" disabled={saving} onClick={()=>void run(()=>decideTitlePreference(workspace.actor_mode,request.id,"REJECT"))}>Reject</button><button className="corp-button" type="button" disabled={saving} onClick={()=>void run(()=>decideTitlePreference(workspace.actor_mode,request.id,"APPROVE"))}>Approve display title</button></div></article>)}</div> : <div className="corp-empty"><BadgeCheck size={24}/><strong>No pending title requests</strong><span>Users can request a preferred display title from their organization profile.</span></div>}</section>
  </main>;
}

function ChainPanel({workspace,saving,initialParent,onClose,onSubmit}:{workspace:ReportingWorkspace;saving:boolean;initialParent:string;onClose:()=>void;onSubmit:(payload:{unit_id:string;parent_position_id:string|null;roles:ChainRoleInput[]})=>Promise<void>}) {
  const editableUnits=workspace.units.filter((unit)=>unit.editable);
  const editablePositions=workspace.positions.filter((position)=>canEditPosition(workspace,position));
  const [unitId,setUnitId]=useState(editableUnits[0]?.id??"");
  const [parentId,setParentId]=useState(initialParent);
  const [roles,setRoles]=useState<ChainDraft[]>([{title:"",code:"",headcount:"1",supervisory:true}]);
  const update=(index:number,patch:Partial<ChainDraft>)=>setRoles((current)=>current.map((item,itemIndex)=>itemIndex===index?{...item,...patch}:item));
  const submit=async(event:FormEvent)=>{event.preventDefault();await onSubmit({unit_id:unitId,parent_position_id:parentId||null,roles:roles.map((role)=>({title:role.title.trim(),code:role.code.trim()||null,headcount_limit:Number(role.headcount||1),is_supervisory:role.supervisory}))});};
  return <aside className="reporting-builder__panel"><header><div><span>Quick hierarchy wizard</span><h2>Add reporting levels</h2></div><button type="button" onClick={onClose}><X size={18}/></button></header><form onSubmit={(event)=>void submit(event)}><label><span>Organization unit</span><select required value={unitId} onChange={(event)=>setUnitId(event.target.value)}>{editableUnits.map((unit)=><option key={unit.id} value={unit.id}>{unit.name}</option>)}</select></label><label><span>Attach beneath</span><select value={parentId} onChange={(event)=>setParentId(event.target.value)}><option value="">Create at top of this chain</option>{editablePositions.map((position)=><option key={position.id} value={position.id}>{position.path_titles.join(" › ")}</option>)}</select></label><div className="reporting-builder__levels"><div><strong>Levels are created top to bottom</strong><small>Example: Supervisor, then Chief Crew, then Engineer.</small></div>{roles.map((role,index)=><article key={index}><span>{index+1}</span><div><input required value={role.title} onChange={(event)=>update(index,{title:event.target.value})} placeholder={index===0?"Supervisor":index===1?"Chief Crew":"Engineer"}/><div><input value={role.code} onChange={(event)=>update(index,{code:event.target.value})} placeholder="Code auto-generated"/><input required type="number" min="1" value={role.headcount} onChange={(event)=>update(index,{headcount:event.target.value})} aria-label="Headcount"/></div><label className="corp-check"><input type="checkbox" checked={role.supervisory} onChange={(event)=>update(index,{supervisory:event.target.checked})}/><span>Can supervise lower levels</span></label></div>{roles.length>1?<button type="button" onClick={()=>setRoles((current)=>current.filter((_,itemIndex)=>itemIndex!==index))}><X size={15}/></button>:null}</article>)}</div><button className="corp-button corp-button--quiet reporting-builder__add-level" type="button" onClick={()=>setRoles((current)=>[...current,{title:"",code:"",headcount:"1",supervisory:current.length<2}])}><Plus size={15}/> Add another level</button><footer><button className="corp-button corp-button--quiet" type="button" onClick={onClose}>Cancel</button><button className="corp-button" type="submit" disabled={saving||!unitId}>{saving?"Creating…":"Create reporting chain"}</button></footer></form></aside>;
}

function AssignmentPanel({workspace,saving,initialPosition,onClose,onSubmit}:{workspace:ReportingWorkspace;saving:boolean;initialPosition:string;onClose:()=>void;onSubmit:(payload:GuidedAssignmentInput)=>Promise<void>}) {
  const positions=workspace.positions.filter((position)=>canEditPosition(workspace,position)&&position.vacancy_count>0);
  const initial=positions.find((item)=>item.id===initialPosition);
  const [userId,setUserId]=useState("");
  const [positionId,setPositionId]=useState(initialPosition);
  const [managerId,setManagerId]=useState(directManager(initial)?.user_id??"");
  const [displayTitle,setDisplayTitle]=useState(initial?.canonical_title??"");
  const [assignmentType,setAssignmentType]=useState("SUBSTANTIVE");
  const [effectiveFrom,setEffectiveFrom]=useState(today);
  const [effectiveTo,setEffectiveTo]=useState("");
  const [matrix,setMatrix]=useState(false);
  const [matrixReason,setMatrixReason]=useState("");
  const [appointmentReference,setAppointmentReference]=useState("");
  const [authorityReference,setAuthorityReference]=useState("");
  const position=positions.find((item)=>item.id===positionId);
  const suggested=directManager(position);
  const choosePosition=(id:string)=>{const next=positions.find((item)=>item.id===id);setPositionId(id);setManagerId(directManager(next)?.user_id??"");setDisplayTitle(next?.canonical_title??"");};
  const submit=async(event:FormEvent)=>{event.preventDefault();await onSubmit({user_id:userId,position_id:positionId,reporting_manager_user_id:managerId||null,assignment_type:assignmentType,is_primary:true,effective_from:effectiveFrom,effective_to:effectiveTo||null,fte_percent:"100",matrix_reporting:matrix,matrix_reason:matrix?matrixReason.trim()||null:null,display_title:displayTitle.trim()||null,appointment_reference:appointmentReference.trim()||null,authority_acceptance_reference:authorityReference.trim()||null,authority_accepted_on:null,delegation_limitations:null});};
  return <aside className="reporting-builder__panel"><header><div><span>Guided placement</span><h2>Assign a person</h2></div><button type="button" onClick={onClose}><X size={18}/></button></header><form onSubmit={(event)=>void submit(event)}><label><span>Person</span><select required value={userId} onChange={(event)=>setUserId(event.target.value)}><option value="">Select person</option>{workspace.users.map((user)=><option key={user.id} value={user.id}>{user.full_name} · {user.staff_code}</option>)}</select></label><label><span>Position</span><select required value={positionId} onChange={(event)=>choosePosition(event.target.value)}><option value="">Select open position</option>{positions.map((item)=><option key={item.id} value={item.id}>{item.path_titles.join(" › ")} · {item.vacancy_count} open</option>)}</select></label><label><span>Actual reporting manager</span><select value={managerId} onChange={(event)=>setManagerId(event.target.value)}><option value="">Auto-map from occupied parent</option>{position?.manager_candidates.map((candidate)=><option key={`${candidate.position_id}-${candidate.user_id}`} value={candidate.user_id}>{candidate.user_name} · {candidate.position_title}</option>)}</select><small>{suggested?`Suggested from direct parent: ${suggested.user_name}`:position?.reports_to_position_id?"Select a manager if the parent has several or no occupants.":"Top positions may have no reporting manager."}</small></label><label><span>Displayed working title</span><input value={displayTitle} onChange={(event)=>setDisplayTitle(event.target.value)} placeholder={position?.canonical_title??"Display title"}/><small>This may differ from the canonical position. It never changes access or aviation authorisation.</small></label><div className="reporting-builder__form-row"><label><span>Assignment type</span><select value={assignmentType} onChange={(event)=>setAssignmentType(event.target.value)}>{["SUBSTANTIVE","ACTING","SECONDMENT","TEMPORARY","INTERIM","INTERNSHIP","APPRENTICESHIP","CONTRACT"].map((item)=><option key={item}>{item}</option>)}</select></label><label><span>Effective from</span><input required type="date" value={effectiveFrom} onChange={(event)=>setEffectiveFrom(event.target.value)}/></label><label><span>Effective to</span><input type="date" value={effectiveTo} onChange={(event)=>setEffectiveTo(event.target.value)}/></label></div><label className="corp-check"><input type="checkbox" checked={matrix} onChange={(event)=>setMatrix(event.target.checked)}/><span>Matrix reporting outside the position chain</span></label>{matrix?<label><span>Matrix reporting reason</span><textarea required rows={2} value={matrixReason} onChange={(event)=>setMatrixReason(event.target.value)}/></label>:null}{position?.is_regulatory_post?<><label><span>Appointment reference</span><input required value={appointmentReference} onChange={(event)=>setAppointmentReference(event.target.value)}/></label>{position.authority_acceptance_required?<label><span>Authority acceptance reference</span><input required value={authorityReference} onChange={(event)=>setAuthorityReference(event.target.value)}/></label>:null}</>:null}<footer><button className="corp-button corp-button--quiet" type="button" onClick={onClose}>Cancel</button><button className="corp-button" type="submit" disabled={saving||!positionId||!userId}><UserPlus size={15}/> {saving?"Assigning…":"Assign and map"}</button></footer></form></aside>;
}

function EditPanel({workspace,position,saving,onClose,onSubmit}:{workspace:ReportingWorkspace;position:ReportingPosition;saving:boolean;onClose:()=>void;onSubmit:(payload:Record<string,unknown>)=>Promise<void>}) {
  const [title,setTitle]=useState(position.canonical_title);
  const [parentId,setParentId]=useState(position.reports_to_position_id??"");
  const [headcount,setHeadcount]=useState(String(position.headcount_limit));
  const [supervisory,setSupervisory]=useState(position.is_supervisory);
  const [syncManagers,setSyncManagers]=useState(true);
  const parents=workspace.positions.filter((item)=>canEditPosition(workspace,item)&&item.id!==position.id);
  const submit=async(event:FormEvent)=>{event.preventDefault();await onSubmit({title:title.trim(),reports_to_position_id:parentId||null,headcount_limit:Number(headcount),is_supervisory:supervisory,sync_reporting_managers:syncManagers});};
  return <aside className="reporting-builder__panel"><header><div><span>Controlled position</span><h2>Edit reporting position</h2></div><button type="button" onClick={onClose}><X size={18}/></button></header><form onSubmit={(event)=>void submit(event)}><label><span>Canonical position title</span><input required value={title} onChange={(event)=>setTitle(event.target.value)}/><small>Approved display-title preferences remain intact when the canonical title changes.</small></label><label><span>Reports to position</span><select value={parentId} onChange={(event)=>setParentId(event.target.value)}><option value="">Top position</option>{parents.map((item)=><option key={item.id} value={item.id}>{item.path_titles.join(" › ")}</option>)}</select></label><div className="reporting-builder__form-row"><label><span>Approved headcount</span><input required type="number" min={Math.max(1,position.occupied_count)} value={headcount} onChange={(event)=>setHeadcount(event.target.value)}/></label><label className="corp-check"><input type="checkbox" checked={supervisory} onChange={(event)=>setSupervisory(event.target.checked)}/><span>Supervisory position</span></label></div><label className="corp-check"><input type="checkbox" checked={syncManagers} onChange={(event)=>setSyncManagers(event.target.checked)}/><span>Automatically map current occupants to the single occupied parent position</span></label>{position.is_regulatory_post?<div className="reporting-builder__notice"><BriefcaseBusiness size={16}/><span>This is a regulatory or nominated position. Tenant-administrator evidence controls still apply.</span></div>:null}<footer><button className="corp-button corp-button--quiet" type="button" onClick={onClose}>Cancel</button><button className="corp-button" type="submit" disabled={saving}><Save size={15}/> {saving?"Saving…":"Save reporting line"}</button></footer></form></aside>;
}
