import React from "react";
import {Link,useParams} from "react-router-dom";
import {getCachedUser} from "../../services/auth";
import ExternalProviderDocumentsReview from "./ExternalProviderDocumentsReview";
import "./external-provider-portal.css";

/** Document Control queue uses the same tenant-scoped submission provenance.
 * Backend enforces appointed DCO permissions for canonical DMS registration.
 */
export default function ExternalProviderDmsPage(){
  const {amoCode=""}=useParams();
  const user=getCachedUser();
  if(user?.role!=="DOCUMENT_CONTROL_OFFICER"){
    return <main className="vendor-card" role="alert">
      <h1>Document Control authorization required</h1>
      <p>This workspace is reserved for appointed Document Control Officers.
        Quality evidence decisions remain available in the Quality workspace.</p>
    </main>;
  }
  return <main className="external-provider-dms">
    <nav aria-label="Document Control"><Link to={`/maintenance/${encodeURIComponent(amoCode)}/document-control`}>
      Document Control workspace</Link></nav>
    <h1>External provider controlled evidence</h1>
    <p>Register a reviewed original under the authoritative DMS evidence and retention lifecycle.
      DMS legal hold and disposition remain governed in Document Control.</p>
    <ExternalProviderDocumentsReview amoCode={amoCode} manager={false}/>
  </main>;
}
