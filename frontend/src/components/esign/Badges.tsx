import React from "react";

const pill = (label: string, tone: "success" | "warning" | "danger" | "neutral") => (
  <span className={`badge badge--${tone}`}>{label}</span>
);

export const PolicyBadge: React.FC<{ level?: string | null }> = ({ level }) => {
  if (!level) return pill("No policy", "neutral");
  if (level.includes("CRYPTO_AND_TIMESTAMP")) return pill("Crypto + Timestamp", "success");
  if (level.includes("CRYPTO")) return pill("Crypto required", "warning");
  if (level.includes("APPEARANCE")) return pill("Appearance allowed", "neutral");
  return pill(level, "neutral");
};

export const TrustBadge: React.FC<{ compliant: boolean; fallback?: boolean }> = ({ compliant, fallback }) => {
  if (!compliant) return pill("Policy non-compliant", "danger");
  if (fallback) return pill("Compliant with fallback", "warning");
  return pill("Policy compliant", "success");
};

export const ValidationBadgeGroup: React.FC<{
  storageIntegrity: boolean;
  cryptoApplied: boolean;
  cryptoValid: boolean;
  timestampPresent: boolean;
}> = ({ storageIntegrity, cryptoApplied, cryptoValid, timestampPresent }) => (
  <div className="esign-badge-row">
    {pill(storageIntegrity ? "Storage integrity verified" : "Storage integrity failed", storageIntegrity ? "success" : "danger")}
    {pill(cryptoApplied ? "Cryptographic signature applied" : "No cryptographic signature", cryptoApplied ? "success" : "warning")}
    {pill(cryptoValid ? "Cryptographic validation passed" : "Cryptographic validation unavailable/failed", cryptoValid ? "success" : "warning")}
    {pill(timestampPresent ? "Timestamp present" : "No timestamp", timestampPresent ? "success" : "neutral")}
  </div>
);

export const HashFingerprintBlock: React.FC<{ label: string; value?: string | null }> = ({ label, value }) => (
  <div className="esign-hash-block">
    <strong>{label}</strong>
    <code>{value || "Unavailable"}</code>
  </div>
);
