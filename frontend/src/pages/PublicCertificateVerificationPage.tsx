import React, { useEffect, useRef, useState } from "react";
import { RefreshCw, ScanLine } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { verifyCertificatePublic, type PublicCertificateVerification } from "../services/training";
import { createHardwareScannerListener, parseScannedCertificate } from "../utils/verificationScan";

const statusLabel = (status?: string) => {
  switch (status) {
    case "VALID": return "Valid";
    case "EXPIRED": return "Expired";
    case "REVOKED": return "Revoked";
    case "SUPERSEDED": return "Superseded";
    case "NOT_FOUND": return "Not Found";
    default: return "Service Unavailable";
  }
};

const PublicCertificateVerificationPage: React.FC = () => {
  const { certificateNumber } = useParams<{ certificateNumber?: string }>();
  const navigate = useNavigate();
  const [value, setValue] = useState(certificateNumber || "");
  const [result, setResult] = useState<PublicCertificateVerification | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const verify = async (certValue: string) => {
    setError(null);
    setResult(null);
    try {
      const data = await verifyCertificatePublic(certValue.trim());
      setResult(data);
    } catch {
      setError("Verification service unavailable");
    }
  };

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    if (certificateNumber) {
      setValue(certificateNumber);
      void verify(certificateNumber);
    }
  }, [certificateNumber]);

  useEffect(() => {
    const listener = createHardwareScannerListener((scanned) => {
      const parsed = parseScannedCertificate(scanned);
      if (parsed) {
        navigate(`/verify/certificate/${encodeURIComponent(parsed)}`);
        setValue(parsed);
      }
    });

    const handleKeyDown = (e: KeyboardEvent) => listener.onKeyDown(e);
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [navigate]);

  return (
    <main style={{ maxWidth: 680, margin: "24px auto", padding: 16 }}>
      <section className="card">
        <h1 style={{ marginTop: 0 }}>Certificate Verification</h1>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <input
            ref={inputRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Certificate number"
            aria-label="Certificate number"
          />
          <button type="button" className="secondary-chip-btn" onClick={() => void verify(value)}>Verify</button>
          <button
            type="button"
            className="secondary-chip-btn"
            aria-label="Scan certificate"
            title="Scan certificate"
            onClick={() => navigate("/verify/scan")}
          >
            <ScanLine size={16} />
          </button>
          <button
            type="button"
            className="secondary-chip-btn"
            aria-label="Retry verification"
            title="Retry"
            onClick={() => void verify(value)}
          >
            <RefreshCw size={16} />
          </button>
        </div>

        {error ? <p style={{ color: "#b42318" }}>{error}</p> : null}

        {result ? (
          <section style={{ marginTop: 16, border: "1px solid var(--line)", borderRadius: 8, padding: 12 }}>
            <p><strong>Status:</strong> {statusLabel(result.status)}</p>
            <p><strong>Certificate:</strong> {result.certificate_number}</p>
            <p><strong>Trainee:</strong> {result.trainee_name || "—"}</p>
            <p><strong>Course:</strong> {result.course_title || "—"}</p>
            <p><strong>Issue date:</strong> {result.issue_date || "—"}</p>
            <p><strong>Valid until:</strong> {result.valid_until || "—"}</p>
            <p><strong>Issuer:</strong> {result.issuer || "—"}</p>
          </section>
        ) : null}
      </section>
    </main>
  );
};

export default PublicCertificateVerificationPage;
