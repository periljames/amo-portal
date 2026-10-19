import React,{useState} from "react";
import type {PartnerProps} from "./ExternalPartnerPage";
import {partnerRequest} from "./partnerApi";
import {Section,State,Status,ActionNotice,usePartnerLoad} from "./PartnerPrimitives";

type Qualification={
  id:string;category:string;case_kind:string;status:string;version:number;
  questionnaire:Array<{key:string;label:string;required?:boolean;kind:string}>;
  answers_json:Record<string,string>;
  can_submit:boolean;next_review_due_on:string|null;
};
type Response={
  items:Qualification[];
  restrictions:Array<{dimension:string;target_key:string;effective_on:string;ends_on:string|null}>;
  approval_notice:string;
};
export default function PartnerQualification({tenant,csrf,capabilities}:PartnerProps){
  const query=usePartnerLoad((signal)=>partnerRequest<Response>(tenant,"qualification",{signal}),tenant);
  const [selected,setSelected]=useState<Qualification|null>(null);
  const [answers,setAnswers]=useState<Record<string,string>>({});
  const [note,setNote]=useState("");
  const [busy,setBusy]=useState(false);
  const [notice,setNotice]=useState("");const [error,setError]=useState("");
  const submit=(event:React.FormEvent)=>{
    event.preventDefault();
    if(!selected)return;
    setBusy(true);setError("");setNotice("");
    void partnerRequest(tenant,"qualification/"+encodeURIComponent(selected.id)+"/answers",{
      method:"POST",csrf,body:{case_version:selected.version,answers,note},
    }).then(()=>{setSelected(null);setAnswers({});setNote("");
      setNotice("Your questionnaire was received for independent Quality review. No approval was granted.");
      query.reload();
    }).catch(e=>setError(e instanceof Error?e.message:"Qualification response rejected"))
      .finally(()=>setBusy(false));
  };
  return <div className="partner-stack">
    <Section title="My Quality qualification" description="Category-specific questionnaires, Quality approval standing and current restrictions. No supplier approval is self-issued.">
      <State pending={query.pending} error={query.error} retry={query.reload}/>
      {query.value?.items.map(item=><article className="partner-row" key={item.id}>
        <div><strong>{item.category} · {item.case_kind}</strong>
          <small>Qualification status {item.status} · Case version {item.version}</small></div>
        <Status value={item.status}/>
        {capabilities.includes("profile.propose")&&item.can_submit&&
          <button type="button" disabled={busy} onClick={()=>{setSelected(item);
            setAnswers(item.answers_json||{});setNote("");setError("");}}>
            Complete questionnaire</button>}
      </article>)}
      {!query.value?.items.length&&!query.pending&&<p className="partner-empty">No qualification request is currently assigned.</p>}
    </Section>
    {selected&&<Section title={"Qualification questionnaire — "+selected.category}
      description="You may submit answers. Only the AMO's appointed Quality and technical authorities may verify evidence or approve scope.">
      <form className="partner-form" onSubmit={submit}>
        {selected.questionnaire.map(q=><label key={q.key}>{q.label||q.key}
          <input required={Boolean(q.required)} maxLength={4000} value={answers[q.key]||""}
            onChange={e=>setAnswers(v=>({...v,[q.key]:e.target.value}))}/></label>)}
        <label>Supporting explanation<textarea required minLength={8} maxLength={2000} rows={3}
          value={note} onChange={e=>setNote(e.target.value)}/></label>
        <div className="partner-buttons"><button className="partner-primary" disabled={busy||note.trim().length<8}>
          {busy?"Submitting…":"Submit answers for Quality review"}</button>
          <button type="button" disabled={busy} onClick={()=>setSelected(null)}>Cancel</button></div>
      </form>
    </Section>}
    <Section title="Current restrictions" description="Only restrictions issued by authorized AMO Quality management are displayed.">
      {query.value?.restrictions.map((x,i)=><div className="partner-row" key={i}>
        <div><strong>{x.dimension} · {x.target_key}</strong>
          <small>Effective {x.effective_on}{x.ends_on?" through "+x.ends_on:" until authorized release"}</small></div>
        <Status value="RESTRICTED"/></div>)}
      {!query.value?.restrictions.length&&<p className="partner-empty">No active scoped restrictions recorded.</p>}
    </Section>
    <ActionNotice value={error} error/><ActionNotice value={notice}/>
  </div>;
}
