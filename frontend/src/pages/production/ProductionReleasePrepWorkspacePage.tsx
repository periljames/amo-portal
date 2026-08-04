import React from "react";
import { useSearchParams } from "react-router-dom";
import { ProductionRecordsHandbackPage } from "./ProductionRecordsHandbackPage";
import { ProductionReleasePrepPage as LegacyReleasePrepPage } from "./ProductionPhaseOnePages";

export const ProductionReleasePrepWorkspacePage: React.FC = () => {
  const [searchParams] = useSearchParams();
  return searchParams.get("view") === "legacy"
    ? <LegacyReleasePrepPage />
    : <ProductionRecordsHandbackPage />;
};
