import React, { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, ShieldCheck } from "lucide-react";
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
  const [code, setCode] = useState("");
  const [compare, setCompare] = useState<{ matches: boolean } | null>(null);
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

  const compareCode = async () => {
    if (!token || !/^[0-9a-fA-F]{64}$/.test(code.trim())) {
      setError("Enter a complete verification code.");
      return;
    }
    setComparing(true); setError(null); setCompare(null);
    try {
      const result = await comparePublicAuditVerificationHash(token, code);
      setCompare({ matches: result.matches });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Verification comparison failed.");
    } finally {
      setComparing(false);
    }
  };

  if (loading) return <main className="qms-public-audit qms-public-audit--center" role="status">Verifying governed audit artifact…</main>;
  if (!data) return <main className="qms-public-audit qms-public-audit--center"><section className="qms-public-audit__message" role="alert"><AlertTriangle size={28} /><h1>Verification unavailable</h1><p>{error || "This verification record could not be established."}</p></section></main>;

  const artifactType = data.assurance_artifact?.artifact_type.replaceAll("_", " ") || "AUDIT REPORT";
  const verified = Boolean(data.report?.status);

  return (
    <main className="qms-public-audit">
      <header className="qms-public-audit__header"><div><span>PUBLIC ARTIFACT VERIFICATION</span><h1>{data.audit.audit_ref} · {data.audit.title}</h1><p>This page confirms whether the linked audit artifact is recorded as issued. It does not expose private audit working papers.</p></div></header>
      <div className="qms-public-audit__content">
        {error ? <div className="qms-public-audit__error" role="alert"><AlertTriangle size={16} /> {error}</div> : null}
        <section className="qms-public-audit__card">
          <header>
            {verified ? <CheckCircle2 size={20} /> : <AlertTriangle size={20} />}
            <div>
              <strong>{verified ? "Verified" : "Not verified"}</strong>
              <small>{verified ? "The verification token resolves to an issued audit record." : "The verification token could not confirm an issued record."}</small>
            </div>
          </header>
          <dl>
            <div><dt>Status</dt><dd>{verified ? "Verified" : "Not verified"}</dd></div>
            <div><dt>Report revision</dt><dd>R{data.report.revision_no} · {data.report.status}</dd></div>
            <div><dt>Issued</dt><dd>{when(data.report.issued_at)}</dd></div>
            <div><dt>Artifact</dt><dd>{artifactType}</dd></div>
            <div><dt>Verification expires</dt><dd>{when(data.verification.expires_at)}</dd></div>
          </dl>
        </section>
        {data.signature ? (
          <section className="qms-public-audit__card">
            <header><ShieldCheck size={20} /><div><strong>Approval recorded</strong><small>A passkey approval was bound to this report revision before issue.</small></div></header>
            <dl>
              <div><dt>Method</dt><dd>{data.signature.method}</dd></div>
              <div><dt>Purpose</dt><dd>{data.signature.purpose.replaceAll("_", " ")}</dd></div>
              <div><dt>Signed</dt><dd>{when(data.signature.signed_at)}</dd></div>
            </dl>
          </section>
        ) : null}
        <section className="qms-public-audit__card">
          <header><ShieldCheck size={20} /><div><strong>Optional check</strong><small>Paste a verification code from a trusted source to confirm it matches this record.</small></div></header>
          <label><span>Verification code</span><input value={code} onChange={(event) => setCode(event.target.value)} maxLength={64} spellCheck={false} autoComplete="off" /></label>
          <button type="button" disabled={comparing} onClick={() => void compareCode()}>{comparing ? "Checking…" : "Check code"}</button>
          {compare ? (
            <div className={compare.matches ? "qms-public-audit__success" : "qms-public-audit__error"} role="status">
              {compare.matches ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
              {compare.matches ? "Verified — code matches this record." : "Not verified — code does not match this record."}
            </div>
          ) : null}
        </section>
      </div>
    </main>
  );
};

export default PublicAuditVerificationPage;
