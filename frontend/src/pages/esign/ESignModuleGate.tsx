import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import SectionCard from "../../components/shared/SectionCard";
import { isEsignEntitled } from "../../services/esign";

const ESignModuleGate: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, setState] = useState<"loading" | "allowed" | "blocked">("loading");

  useEffect(() => {
    isEsignEntitled().then((ok) => setState(ok ? "allowed" : "blocked")).catch(() => setState("blocked"));
  }, []);

  if (state === "loading") return <SectionCard title="E-Signatures">Loading entitlement…</SectionCard>;
  if (state === "blocked") {
    return (
      <SectionCard title="E-Signatures module unavailable" subtitle="This area requires ESIGN_MODULE entitlement.">
        <p>Upgrade your subscription to access E-Sign operator and signer flows.</p>
        <Link to="/pricing">View plans</Link>
      </SectionCard>
    );
  }
  return <>{children}</>;
};

export default ESignModuleGate;
