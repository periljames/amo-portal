import React, { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Fingerprint, Hash, ShieldCheck } from "lucide-react";
import { useLocation } from "react-router-dom";

import { comparePublicAuditVerificationHash, getPublicAuditVerification, type PublicAuditVerification } from "../services/qmsAuditVerification";
import "../styles/qms-public-audit-access.css";

function tokenFromPath(pathname: string): string | null {
  const match = pathname.match(/^\/verify\/([^/]+)\/?$/i);
  return match ? decodeURIComponent(match[1]) : null;
}

function when(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

const PublicAuditVerificationPage: React.FC = () => {
  const location = useLocation();
  const token = useMemo(() => tokenFromPath(location.pathname), [location.pathname]);
  const [data, setData] = useState<PublicAuditVerification | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hash, setHash] = useState("");
  const [compare, setCompare] = useState<{ matches: boolean; governed_sha256: string; artifact_type: string } | null>(null);
  const [comparing, setComparing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (!token) { setError("Verification token is missing."); setLoading(false); return; }
      setLoading(true); setError(null);
      try {
        const next = await getPublicAuditVerification(token);
        if (!cancelled) setData(next);
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "Verification record unavailable.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [token]);

  const compareHash = async () => {
    if (!token || !/^[0-9a-fA-F]{64}$/.test(hash.trim())) {
      setError("Enter a complete 64-character SHA-256 value.");
      return;
    }
    setComparing(true); setError(null); setCompare(null);
    try { setCompare(await comparePublicAuditVerificationHash(token, hash)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Hash comparison failed."); }
    finally { setComparing(false); }
  };

  if (loading) return <main className="qms-public-audit qms-public-audit--center" role="status">Verifying governed audit artifact…</main>;
  if (!data) return <main className="qms-public-audit qms-public-audit--center"><section className="qms-public-audit__message" role="alert"><AlertTriangle size={28} /><h1>Verification unavailable</h1><p>{error || "This verification record could not be established."}</p></section></main>;

  const governedHash = data.assurance_artifact?.sha256 || data.report.sha256;
  const artifactType = data.assurance_artifact?.artifact_type.replaceAll("_", " ") || "AUDIT REPORT";

  return (
    <main className="qms-public-audit">
      <header className="qms-public-audit__header"><div><span>PUBLIC GOVERNED ARTIFACT VERIFICATION</span><h1>{data.audit.audit_ref} · {data.audit.title}</h1><p>Verification confirms the recorded governed hash and passkey ceremony. It does not expose private audit working papers.</p></div></header>
      <div className="qms-public-audit__content">
        {error ? <div className="qms-public-audit__error" role="alert"><AlertTriangle size={16} /> {error}</div> : null}
        <section className="qms-public-audit__card">
          <header><ShieldCheck size={20} /><div><strong>Valid governed record</strong><small>The verification token is active and the report/signature chain resolves to the issued audit.</small></div></header>
          <dl>
            <div><dt>Report revision</dt><dd>R{data.report.revision_no} · {data.report.status}</dd></div>
            <div><dt>Issued</dt><dd>{when(data.report.issued_at)}</dd></div>
            <div><dt>Artifact verified</dt><dd>{artifactType}</dd></div>
            <div><dt>Verification expires</dt><dd>{when(data.verification.expires_at)}</dd></div>
            <div className="is-wide"><dt>Governed SHA-256</dt><dd><code>{governedHash}</code></dd></div>
          </dl>
        </section>
        <section className="qms-public-audit__card">
          <header><Fingerprint size={20} /><div><strong>Passkey approval evidence</strong><small>The approval was bound to the governed report revision before issue.</small></div></header>
          <dl><div><dt>Method</dt><dd>{data.signature.method}</dd></div><div><dt>Purpose</dt><dd>{data.signature.purpose.replaceAll("_", " ")}</dd></div><div><dt>Signed</dt><dd>{when(data.signature.signed_at)}</dd></div><div className="is-wide"><dt>Ceremony SHA-256</dt><dd><code>{data.signature.ceremony_sha256 || "—"}</code></dd></div></dl>
        </section>
        <section className="qms-public-audit__card">
          <header><Hash size={20} /><div><strong>Compare a downloaded artifact hash</strong><small>Compute the file SHA-256 locally and compare it without uploading the document itself.</small></div></header>
          <label><span>SHA-256</span><input value={hash} onChange={(event) => setHash(event.target.value)} maxLength={64} spellCheck={false} /></label>
          <button type="button" disabled={comparing} onClick={() => void compareHash()}>{comparing ? "Comparing…" : "Compare hash"}</button>
          {compare ? <div className={compare.matches ? "qms-public-audit__success" : "qms-public-audit__error"} role="status">{compare.matches ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}{compare.matches ? "Hash matches the governed artifact." : "Hash does not match the governed artifact."}</div> : null}
        </section>
      </div>
    </main>
  );
};

export default PublicAuditVerificationPage;
