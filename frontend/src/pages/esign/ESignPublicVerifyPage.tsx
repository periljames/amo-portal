import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import AuthLayout from "../../components/Layout/AuthLayout";
import { HashFingerprintBlock, ValidationBadgeGroup } from "../../components/esign/Badges";
import InlineLoader from "../../components/loading/InlineLoader";
import PageLoader from "../../components/loading/PageLoader";
import { useAsyncWithLoader } from "../../hooks/useAsyncWithLoader";
import { comparePublicHash, fetchPublicArtifactAccess, publicArtifactDownloadUrl, verifyToken } from "../../services/esign";
import type { ArtifactAccess, HashCompareResult, VerifyResult } from "../../types/esign";

const ESignPublicVerifyPage: React.FC = () => {
  const { token = "" } = useParams();
  const withLoader = useAsyncWithLoader();
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [missing, setMissing] = useState(false);
  const [serverError, setServerError] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [artifactAccess, setArtifactAccess] = useState<ArtifactAccess | null>(null);
  const [compareHash, setCompareHash] = useState("");
  const [compareResult, setCompareResult] = useState<HashCompareResult | null>(null);
  const [compareBusy, setCompareBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    void withLoader(
      async () => {
        try {
          const data = await verifyToken(token);
          const access = await fetchPublicArtifactAccess(token).catch(() => null);
          if (cancelled) return;
          setResult(data);
          setArtifactAccess(access);
          setMissing(false);
          setServerError(false);
        } catch (error) {
          if (cancelled) return;
          setResult(null);
          setArtifactAccess(null);
          const message = error instanceof Error ? error.message : "";
          if (message.includes("404") || message.includes("Not found")) {
            setMissing(true);
            setServerError(false);
          } else {
            setMissing(false);
            setServerError(true);
          }
        } finally {
          if (!cancelled) {
            setIsLoading(false);
          }
        }
      },
      {
        scope: "public-verify",
        label: "Loading verification record",
        phase: "verifying",
        message: "Checking verification status",
        allow_overlay: true,
        mode_preference: "page",
        affects_route: true,
      }
    );

    return () => {
      cancelled = true;
    };
  }, [token, withLoader]);

  const compare = async () => {
    try {
      setCompareBusy(true);
      const compared = await withLoader(
        () => comparePublicHash(token, { provided_sha256: compareHash, compare_against: "artifact" }),
        {
          scope: "public-compare",
          label: "Comparing fingerprint",
          phase: "validating",
          message: "Comparing provided hash against verified artifact fingerprint",
        }
      );
      setCompareResult(compared);
    } catch {
      setCompareResult(null);
    } finally {
      setCompareBusy(false);
    }
  };

  return (
    <AuthLayout title="E-Sign verification" subtitle="Public verification result">
      {isLoading ? (
        <PageLoader
          title="Loading verification record"
          subtitle="Checking verification status"
          phase="verifying"
          message="Please wait while we validate the verification token."
          contrast="high"
        />
      ) : (
        <section className="panel">
          {missing && <h2>Verification record not found</h2>}
          {serverError && <h2>Verification service temporarily unavailable</h2>}
          {result && (
            <>
              <h2>{result.title || "Signature verification"}</h2>
              <p>This file hash check and cryptographic signature check are displayed separately.</p>
              <ValidationBadgeGroup
                storageIntegrity={result.storage_integrity_valid}
                cryptoApplied={result.cryptographic_signature_applied}
                cryptoValid={result.cryptographically_valid}
                timestampPresent={result.timestamp_present}
              />
              <HashFingerprintBlock label="Document SHA-256" value={result.document_sha256} />
              <HashFingerprintBlock label="Artifact SHA-256" value={result.artifact_sha256} />
              <h3>Artifact access</h3>
              {artifactAccess ? (
                <>
                  <p>
                    {artifactAccess.public_download_allowed
                      ? "Public artifact download is available."
                      : "This verification record is valid, but document download is not publicly available."}
                  </p>
                  {artifactAccess.public_download_allowed && <a href={publicArtifactDownloadUrl(token)}>Download verified artifact</a>}
                </>
              ) : (
                <p>Artifact access information unavailable.</p>
              )}
              <h3>Compare fingerprint</h3>
              <input value={compareHash} onChange={(e) => setCompareHash(e.target.value)} placeholder="Paste SHA-256 to compare" />
              <button type="button" onClick={() => void compare()} disabled={compareBusy || !compareHash.trim()}>
                {compareBusy ? <InlineLoader label="Comparing" /> : "Compare"}
              </button>
              {compareResult && (
                <p>
                  {compareResult.message}: {compareResult.match ? "MATCH" : "NO MATCH"}
                </p>
              )}
            </>
          )}
        </section>
      )}
    </AuthLayout>
  );
};

export default ESignPublicVerifyPage;
