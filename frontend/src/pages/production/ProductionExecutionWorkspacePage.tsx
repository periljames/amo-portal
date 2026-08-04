import React from "react";
import { useSearchParams } from "react-router-dom";
import { ProductionExecutionControlPage } from "./ProductionExecutionControlPage";
import { ProductionExecutionPage as LegacyExecutionPage } from "./ProductionPhaseOnePages";

export const ProductionExecutionWorkspacePage: React.FC = () => {
  const [searchParams] = useSearchParams();
  return searchParams.get("view") === "legacy"
    ? <LegacyExecutionPage />
    : <ProductionExecutionControlPage />;
};
