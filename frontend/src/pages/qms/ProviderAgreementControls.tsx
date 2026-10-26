import React,{useEffect,useState} from "react";
import {apiRequest} from "../../services/apiClient";
import type {ProviderContract} from "../../services/qmsProviders";
import TextItemList from "../../components/forms/TextItemList";

type DmsRevision={id:string;code:string;title:string;revision_id:string;rev_number:string};
type SignedFile={id:string;filename:string;sha256:string;status:string;quality_status:string|null};
type Agreement=ProviderContract&{
  counterparties_json:string[]|null;approved_sites_json:string[]|null;
  authority_acceptance_reference:string|null;signed_evidence_submission_id:string|null;
};
function message(e:unknown){return e instanceof Error?e.message:"Agreement request was not accepted";}
export default function ProviderAgreementControls({amoCode,contract,onChanged}:{
  amoCode:string;contract:ProviderContract;onChanged:()=>Promise<void>;
}){
  const root=`/api/maintenance/${encodeURIComponent(amoCode)}/quality/external-accounts/documents`;
  const [open,setOpen]=useState(false);const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");const [notice,setNotice]=useState("");
  const [agreement,setAgreement]=useState<Agreement|null>(null);
  const [dms,setDms]=useState<DmsRevision[]>([]);const [evidence,setEvidence]=useState<SignedFile[]>([]);
  const [parties,setParties]=useState<string[]>([]);const [sites,setSites]=useState<string[]>([]);
  const [manualRev,setManualRev]=useState("");const [signedId,setSignedId]=useState("");
  const [authority,setAuthority]=useState("");const [renewal,setRenewal]=useState("");
  const [noticeDays,setNoticeDays]=useState("");
  useEffect(()=>{
    if(!open)return;
    let active=true;
    setError("");setNotice("");
    void Promise.all([
      apiRequest<Agreement>(`${root}/contracts/${encodeURIComponent(contract.id)}/controls`,{cacheTtlMs:0}),
      apiRequest<{items:DmsRevision[]}>(`${root}/dms-options?limit=100`,{cacheTtlMs:0}),
      apiRequest<{items:SignedFile[]}>(`${root}/contracts/${encodeURIComponent(contract.id)}/candidate-evidence`,{cacheTtlMs:0}),
    ]).then(([a,d,s])=>{
      if(!active)return;
      setAgreement(a);setDms(d.items);setEvidence(s.items);
      setParties(a.counterparties_json||[]);
      setSites(a.approved_sites_json||[]);
      const matched=d.items.find(x=>x.id===a.controlled_document_id &&
        (x.revision_id===a.controlled_document_revision||x.rev_number===a.controlled_document_revision));
      setManualRev(matched?.revision_id||"");
      setSignedId(a.signed_evidence_submission_id||"");
      setAuthority(a.authority_acceptance_reference||"");
      setRenewal(a.renewal_terms||"");
      setNoticeDays(a.termination_notice_days==null?"":String(a.termination_notice_days));
    }).catch(e=>{if(active)setError(message(e));});
    return()=>{active=false;};
  },[open,amoCode,contract.id,root]);
  async function save(e:React.FormEvent){
    e.preventDefault();
    if(!agreement)return;
    const chosen=dms.find(x=>x.revision_id===manualRev);
    if(!chosen){setError("Choose a current published DMS revision.");return;}
    const counterparties=parties.map(x=>x.trim()).filter(Boolean);
    const approved_sites=sites.map(x=>x.trim()).filter(Boolean);
    if(counterparties.length<2||!signedId){setError("Two counterparties and a signed evidence submission are required.");return;}
    setBusy(true);setError("");setNotice("");
    try{
      await apiRequest(`${root}/contracts/${encodeURIComponent(contract.id)}/controls`,{
        method:"PATCH",body:JSON.stringify({
          expected_version:agreement.version,
          counterparties,approved_sites,
          authority_acceptance_reference:authority.trim()||null,
          controlled_document_id:chosen.id,controlled_document_revision:chosen.revision_id,
          signed_evidence_submission_id:signedId,
          renewal_terms:renewal.trim()||null,
          termination_notice_days:noticeDays?Number(noticeDays):null,
        }),
      });
      setNotice("Signed agreement controls recorded. Quality evidence must be independently verified before contract activation.");
      await onChanged();setOpen(false);
    }catch(err){setError(message(err));}finally{setBusy(false);}
  }
  return <div className="qms-provider-record__controls">
    <button type="button" disabled={busy} onClick={()=>setOpen(!open)}>
      {open?"Close agreement controls":"Executed agreement & DMS controls"}
    </button>
    {open&&<form className="qms-provider-form qms-provider-inline-form" onSubmit={e=>void save(e)}>
      {contract.status!=="DRAFT"&&<p>Executed agreement metadata is locked. Use a new amendment or renewal rather than editing the signed revision.</p>}
      <div className="is-wide"><TextItemList label="Counterparty legal entities" required value={parties} onChange={setParties} disabled={busy} /></div>
      <TextItemList label="Approved sites" value={sites} onChange={setSites} disabled={busy} />
      <label className="is-wide">Signed agreement — current published DMS original
        <select required value={manualRev} onChange={e=>setManualRev(e.target.value)}>
          <option value="">Choose controlled revision</option>
          {dms.map(d=><option key={d.revision_id} value={d.revision_id}>{d.code} / {d.title} / {d.rev_number}</option>)}
        </select></label>
      <label className="is-wide">Accepted signed-file submission (original hash must match DMS)
        <select required value={signedId} onChange={e=>setSignedId(e.target.value)}>
          <option value="">Choose accepted contract-scoped evidence</option>
          {evidence.map(s=><option key={s.id} value={s.id}>{s.filename} · QMS {s.quality_status||"pending"} · {s.sha256.slice(0,12)}</option>)}
        </select></label>
      <label>Relevant authority acceptance reference
        <input value={authority} onChange={e=>setAuthority(e.target.value)}/></label>
      <label>Renewal conditions
        <textarea value={renewal} rows={2} onChange={e=>setRenewal(e.target.value)}/></label>
      <label>Termination notice period in days
        <input type="number" min={0} max={3650} value={noticeDays} onChange={e=>setNoticeDays(e.target.value)}/></label>
      {error&&<p role="alert">{error}</p>}
      {notice&&<p role="status">{notice}</p>}
      <p>The agreement status remains separate from provider Quality approval and work authorization. Prior signed revisions remain in DMS.</p>
      <button type="submit" disabled={busy||!agreement||contract.status!=="DRAFT"}>
        {busy?"Saving…":"Save executed agreement controls"}
      </button>
    </form>}
  </div>;
}
