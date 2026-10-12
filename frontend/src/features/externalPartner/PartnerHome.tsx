import React from "react";
import {Link} from "react-router-dom";
import type {PartnerProps} from "./ExternalPartnerPage";
import {partnerRequest,friendlyDate,label,type Summary} from "./partnerApi";
import {Section,State,Status,usePartnerLoad} from "./PartnerPrimitives";

export default function PartnerHome({tenant}:PartnerProps){
  const query=usePartnerLoad((signal)=>partnerRequest<Summary>(tenant,"home",{signal}),tenant);
  const data=query.value;
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
      <Section title="Open partner workflows" description="Operational work is shown only when assigned in the current Quality-approved grant.">
        <div className="partner-shortcuts">
          <Link to={`/partner/${tenant}/quality`}>Assigned audits, requests & CARs</Link>
          <Link to={`/partner/${tenant}/procurement`}>RFQs, POs & delivery commitments</Link>
          <Link to={`/partner/${tenant}/activity`}>Notifications and attributable history</Link>
        </div>
      </Section>
    </>}
  </div>;
}
