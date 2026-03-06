import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import PageHeader from "../../components/shared/PageHeader";
import SectionCard from "../../components/shared/SectionCard";
import { ValidationBadgeGroup } from "../../components/esign/Badges";
import InlineLoader from "../../components/loading/InlineLoader";
import SectionLoader from "../../components/loading/SectionLoader";
import { useAsyncWithLoader } from "../../hooks/useAsyncWithLoader";
import { getCachedUser } from "../../services/auth";
import {
  comparePrivateHash,
  fetchArtifactValidation,
  fetchArtifactVerifyLink,
  fetchPrivateArtifactAccess,
  privateArtifactDownloadUrl,
  privateArtifactPreviewUrl,
  regenerateArtifactVerifyLink,
  revalidateArtifact,
} from "../../services/esign";
import type { ArtifactAccess, ArtifactValidation, ArtifactVerifyLink, HashCompareResult } from "../../types/esign";
import ESignModuleGate from "./ESignModuleGate";

const ESignArtifactValidationPage: React.FC = () => {
  const { artifactId = "" } = useParams();
  const withLoader = useAsyncWithLoader();
  const [data, setData] = useState<ArtifactValidation | null>(null);
  const [verifyLink, setVerifyLink] = useState<ArtifactVerifyLink | null>(null);
  const [access, setAccess] = useState<ArtifactAccess | null>(null);
  const [compareHash, setCompareHash] = useState("");
  const [compareResult, setCompareResult] = useState<HashCompareResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingPage, setLoadingPage] = useState(false);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const currentUser = getCachedUser();
  const isAdmin = Boolean(currentUser?.is_superuser || currentUser?.is_amo_admin);

  const load = async () => {
    try {
      setLoadingPage(true);
      await withLoader(
        async () => {
          const [validation, link, artifactAccess] = await Promise.all([
            fetchArtifactValidation(artifactId),
            fetchArtifactVerifyLink(artifactId),
            fetchPrivateArtifactAccess(artifactId),
          ]);
          setData(validation);
          setVerifyLink(link);
          setAccess(artifactAccess);
          setError(null);
        },
        {
          scope: "esign-artifact",
          label: "Loading artifact validation",
          phase: "loading",
          message: "Retrieving validation, verify-link, and access controls",
          mode_preference: "section",
          allow_overlay: true,
        }
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoadingPage(false);
    }
  };

  useEffect(() => {
    void load();
  }, [artifactId]);

  const revalidate = async () => {
    try {
      setActionBusy("revalidate");
      const validated = await withLoader(() => revalidateArtifact(artifactId), {
        scope: "esign-artifact",
        label: "Revalidating artifact",
        phase: "verifying",
        mode_preference: "section",
        allow_overlay: true,
      });
      setData(validated);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setActionBusy(null);
    }
  };

  const regenerate = async () => {
    try {
      setActionBusy("regenerate");
      const refreshedLink = await withLoader(() => regenerateArtifactVerifyLink(artifactId), {
        scope: "esign-artifact",
        label: "Regenerating verification link",
        phase: "generating",
        mode_preference: "inline",
      });
      setVerifyLink(refreshedLink);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setActionBusy(null);
    }
  };

  const compare = async () => {
    try {
      setActionBusy("compare");
      const compared = await withLoader(
        () => comparePrivateHash(artifactId, { provided_sha256: compareHash, compare_against: "artifact" }),
        {
          scope: "esign-artifact",
          label: "Comparing provided fingerprint",
          phase: "validating",
          mode_preference: "section",
          allow_overlay: true,
        }
      );
      setCompareResult(compared);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setActionBusy(null);
    }
  };

  return (
    <ESignModuleGate>
      <PageHeader title={`Artifact ${artifactId}`} subtitle="Storage integrity and cryptographic validation are shown independently." />
      {loadingPage && <SectionLoader title="Loading artifact status" message="Checking integrity, policy, and access controls" phase="loading" />}
      <SectionCard title="Validation status">
        {data && (
          <ValidationBadgeGroup
            storageIntegrity={data.storage_integrity_valid}
            cryptoApplied={data.signature_present}
            cryptoValid={data.cryptographically_valid}
            timestampPresent={data.timestamp_present}
          />
        )}
        <p>{error || `Validation status: ${data?.cryptographic_validation_status || "unknown"}`}</p>
        <button type="button" onClick={() => void revalidate()} disabled={!!actionBusy}>
          {actionBusy === "revalidate" ? <InlineLoader label="Revalidating" /> : "Revalidate now"}
        </button>
      </SectionCard>
      <SectionCard title="Verification link">
        <p>Token status: {verifyLink?.token_status || "unknown"}</p>
        <code>{verifyLink?.public_verify_url || "Unavailable"}</code>
        <div className="esign-actions">
          {verifyLink?.public_verify_url && (
            <a href={verifyLink.public_verify_url} target="_blank" rel="noreferrer">
              Open public verify
            </a>
          )}
          {verifyLink?.public_verify_url && (
            <button type="button" onClick={() => void navigator.clipboard.writeText(verifyLink.public_verify_url)}>
              Copy link
            </button>
          )}
          {isAdmin && (
            <button type="button" onClick={() => void regenerate()} disabled={!!actionBusy}>
              {actionBusy === "regenerate" ? <InlineLoader label="Regenerating" /> : "Regenerate token"}
            </button>
          )}
          {access?.preview_allowed && (
            <a href={privateArtifactPreviewUrl(artifactId)} target="_blank" rel="noreferrer">
              Preview artifact
            </a>
          )}
          {access?.download_allowed && (
            <a href={privateArtifactDownloadUrl(artifactId)} target="_blank" rel="noreferrer">
              Download artifact
            </a>
          )}
        </div>
      </SectionCard>
      <SectionCard title="Compare fingerprint">
        <p>Compare a local file hash against the authoritative signed artifact fingerprint.</p>
        <input value={compareHash} onChange={(e) => setCompareHash(e.target.value)} placeholder="Paste SHA-256" />
        <div className="esign-actions">
          <button type="button" onClick={() => void compare()} disabled={!!actionBusy || !compareHash.trim()}>
            {actionBusy === "compare" ? <InlineLoader label="Comparing" /> : "Compare hash"}
          </button>
        </div>
        {compareResult && (
          <p>
            {compareResult.message}: {compareResult.match ? "MATCH" : "NO MATCH"}
          </p>
        )}
      </SectionCard>
    </ESignModuleGate>
  );
};

export default ESignArtifactValidationPage;
