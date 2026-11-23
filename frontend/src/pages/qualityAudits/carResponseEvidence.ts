import type { CARAttachmentOut } from '../../services/qms';
import type { CarRcaProjection } from '../../services/qmsCarRca';
export type ResponseSection='CONTAINMENT'|'ROOT_CAUSE'|'CORRECTIVE';
export const RESPONSE_SECTIONS:{value:ResponseSection;label:string}[]=[{value:'CONTAINMENT',label:'Immediate action'},{value:'ROOT_CAUSE',label:'Root cause'},{value:'CORRECTIVE',label:'Corrective Action (CAP)'}];
export function sectionEvidence(files:CARAttachmentOut[],projection:CarRcaProjection|null,section:ResponseSection,narrative?:string|null) {
 const doc=projection?.submitted_snapshot?.investigation??projection?.draft.investigation;
 const refs=section==='ROOT_CAUSE'?[...(doc?.conclusion_evidence_references||[]),...(doc?.investigations||[]).flatMap(method=>method.nodes.flatMap(node=>node.evidence_references))]:(projection?.actions||[]).filter(action=>action.kind===section).flatMap(action=>action.evidence_references);
 return files.filter(file=>file.response_section===section||refs.includes(`CAR-ATTACHMENT:${file.id}`)||refs.includes(file.id)||Boolean(narrative&&(narrative.includes(`CAR-ATTACHMENT:${file.id}`))));
}
export function decision(status?:string|null) {
 const state=(status||'').toUpperCase();
 if(['ACCEPTED','APPROVED','VERIFIED'].includes(state))return {label:'Accepted',tone:'accepted'};
 if(state==='REJECTED')return {label:'Rejected',tone:'rejected'};
 if(state==='NEEDS_EVIDENCE')return {label:'More evidence needed',tone:'rejected'};
 if(state==='SUBMITTED')return {label:'Awaiting review',tone:'pending'};
 return {label:'Not reviewed',tone:'pending'};
}
