import React from "react";
import {Link} from "react-router-dom";
import type {PartnerProps} from "./ExternalPartnerPage";
import {partnerRequest,friendlyDate,label,type Summary} from "./partnerApi";
import {Section,State,Status,usePartnerLoad} from "./PartnerPrimitives";

export default function PartnerHome({tenant,capabilities}:PartnerProps){
  const query=usePartnerLoad((signal)=>partnerRequest<Summary>(tenant,"home",{signal}),tenant);
  const data=query.value;
  const visibleTasks=(data?.urgent_tasks||[]).filter(task=>
    task.to==="quality"
      ? capabilities.includes("task.read")||capabilities.includes("capa.respond")
      : capabilities.includes("task.read"));
  return <div className="partner-stack">
    <State pending={query.pending} error={query.error} retry={query.reload}/>
    {data&&<>
      <div className="partner-kpi-grid" aria-label="Provider action center summary">
        <Link to={`/partner/${tenant}/organization`} className="partner-kpi">
          <small>Canonical supplier approval</small><strong>{label(data.supplier.status)}</strong>
          <span>{data.supplier.supplier_code}</span>
        </Link>
        <Link to={`/partner/${tenant}/compliance`} className="partner-kpi">
          <small>Certificates expiring in 60 days</small><strong>{data.expiring_certificates.length}</strong>
          <span>Review certificates and submit renewals</span>
        </Link>
        <Link to={`/partner/${tenant}/organization`} className="partner-kpi">
          <small>Pending change proposals</small><strong>{data.open_change_requests}</strong>
          <span>Awaiting authorized review</span>
        </Link>
        <Link to={`/partner/${tenant}/activity`} className="partner-kpi">
          <small>Unread notifications</small><strong>{data.unread_notifications}</strong>
          <span>Account and submission events</span>
        </Link>
      </div>
      <Section title="Provider standing" description="These statuses come from the current Procurement supplier and Quality portal records.">
        <div className="partner-inline"><span>Supplier</span><Status value={data.supplier.status}/></div>
        <div className="partner-inline"><span>External portal</span><Status value={data.supplier.portal_state}/></div>
        <div className="partner-inline"><span>Additional restrictions</span><strong>{data.supplier.restrict_new_work?"New work blocked":"See approved scope"}</strong></div>
        <div className="partner-inline"><span>Next Quality review</span><strong>{friendlyDate(data.supplier.review_due)}</strong></div>
      </Section>
      <div className="partner-columns">
        <Section title="Upcoming renewal actions" description="Upcoming expiry dates, not an automatic approval decision.">
          {data.actions.length?data.actions.map((item,index)=><Link className="partner-action" key={`${item.kind}-${index}`}
            to={`/partner/${tenant}/${item.to}`}>
            <div><strong>{item.title}</strong><small>Due {friendlyDate(item.due)}</small></div><span>Review →</span>
          </Link>):<p className="partner-empty">No certificate renewals due in the next 60 days.</p>}
        </Section>
        <Section title="Agreements nearing expiry">
          {data.expiring_contracts.length?data.expiring_contracts.map((item)=>
            <Link key={item.id} className="partner-action" to={`/partner/${tenant}/contracts`}>
              <div><strong>{item.title}</strong><small>{item.contract_number} · {friendlyDate(item.expires_on)}</small></div><Status value={item.status}/>
            </Link>):<p className="partner-empty">No assigned agreements currently nearing expiry.</p>}
        </Section>
      </div>
      <div className="partner-columns">
        <Section title="Current approved scope" description="Live categories under the canonical Procurement supplier approval register.">
          {data.approved_scope.length?data.approved_scope.map((x,i)=><div key={i} className="partner-row">
            <div><strong>{x.category} · {x.product_family}</strong>
              <small>{x.site_code} · {x.approval_number||"Scope reference not recorded"}</small></div></div>)
            :<p className="partner-empty">No currently ACTIVE approval scopes.</p>}
        </Section>
        <Section title="Most recent notifications">
          {data.recent_notifications.length?data.recent_notifications.map(x=><Link
            to={`/partner/${tenant}/activity`} key={x.id} className="partner-action">
            <div><strong>{x.title}</strong><small>{x.category} · {friendlyDate(x.created_at)}</small></div>
            {!x.read_at&&<span>Unread</span>}
          </Link>):<p className="partner-empty">No portal notifications yet.</p>}
        </Section>
      </div>
      <Section title="Upcoming assigned deadlines" description="Current RFQ, PO, audit and released corrective-action commitments.">
        {visibleTasks.length?visibleTasks.map((x,i)=>
          <Link key={`${x.kind}-${i}`} to={`/partner/${tenant}/${x.to}`} className="partner-action">
            <div><strong>{x.title}</strong><small>{label(x.kind)} · Due {friendlyDate(x.due)}</small></div>
            <span>View</span>
          </Link>):<p className="partner-empty">No overdue or upcoming assigned tasks.</p>}
      </Section>
      <Section title="Outstanding assigned work" description="Counts are calculated in the authoritative Procurement and QMS registers for your approved assignment, not static dashboard figures.">
        <div className="partner-shortcuts">
          {capabilities.includes("task.read")&&<>
            <Link to={`/partner/${tenant}/procurement`}>RFQs awaiting quotation <strong>{data.outstanding_tasks.rfqs}</strong></Link>
            <Link to={`/partner/${tenant}/procurement`}>PO acknowledgements pending <strong>{data.outstanding_tasks.purchase_orders}</strong></Link>
            <Link to={`/partner/${tenant}/quality`}>Audit document requests <strong>{data.outstanding_tasks.audit_requests}</strong></Link>
          </>}
          {(capabilities.includes("task.read")||capabilities.includes("capa.respond"))&&
            <Link to={`/partner/${tenant}/quality`}>Released open CARs <strong>{data.outstanding_tasks.cars}</strong></Link>}
          <Link to={`/partner/${tenant}/activity`}>Notifications & attributable history →</Link>
        </div>
      </Section>
    </>}
  </div>;
}
