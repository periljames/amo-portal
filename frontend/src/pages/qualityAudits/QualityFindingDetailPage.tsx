import React from "react";
import FindingCaseView from "./FindingCaseView";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, Link2 } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { getContext } from "../../services/auth";
import { ApiClientError } from "../../services/apiClient";
import { qmsGetAuditRegisterPage } from "../../services/qmsRegisters";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";
import { primaryLinkedCar } from "./findingLifecycle";

const QualityFindingDetailPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string; findingId?: string }>();
  const navigate = useNavigate();
  const context = getContext();
  const amoCode = params.amoCode ?? context.amoCode ?? "UNKNOWN";
  const findingId = params.findingId?.trim() || "";

  const detailQuery = useQuery({
    queryKey: ["qms-finding-detail", amoCode, findingId],
    queryFn: ({ signal }) => qmsGetAuditRegisterPage({
      amoCode,
      findingId,
      limit: 1,
      offset: 0,
      signal,
    }),
    enabled: Boolean(findingId),
    staleTime: 15_000,
    retry: (failureCount, error) => !(error instanceof ApiClientError && [401, 403, 404].includes(error.status)) && failureCount < 1,
  });

  const invalidResponse = Boolean(detailQuery.data && !Array.isArray(detailQuery.data.rows));
  const row = detailQuery.data?.rows?.[0];
  const finding = row?.finding;
  const audit = row?.audit;
  const linkedCars = row?.linked_cars ?? [];
  const car = primaryLinkedCar(linkedCars);
  const unauthorized = detailQuery.error instanceof ApiClientError
    && [401, 403].includes(detailQuery.error.status);

  return (
    <QualityAuditsSectionLayout
      title={finding?.finding_ref || "Finding detail"}
      subtitle=""
    >
      <div className="audit-workspace qa-finding-detail">
        <button
          type="button"
          className="qa-finding-detail__back"
          onClick={() => navigate(`/maintenance/${amoCode}/quality/audits/register?tab=findings`)}
        >
          <ArrowLeft size={15} /> Findings
        </button>

        {detailQuery.isLoading ? (
          <div className="audit-panel qa-finding-detail__state" role="status">Loading finding…</div>
        ) : unauthorized ? (
          <div className="audit-panel qa-finding-detail__state" role="alert">
            <AlertTriangle size={20} />
            <div><strong>Not authorized</strong><p>You do not have access to this finding.</p></div>
          </div>
        ) : detailQuery.isError || invalidResponse ? (
          <div className="audit-panel qa-finding-detail__state" role="alert">
            <AlertTriangle size={20} />
            <div>
              <strong>Finding could not be loaded</strong>
              <p>
                {/uuid_parsing|valid UUID/i.test(detailQuery.error instanceof Error ? detailQuery.error.message : "")
                  ? "This finding link is invalid. Open Findings and select a finding from the register."
                  : detailQuery.error instanceof Error
                    ? detailQuery.error.message
                    : "The finding register returned an incomplete record. Retry to reload it."}
              </p>
              <button type="button" className="secondary-chip-btn" onClick={() => void detailQuery.refetch()}>Retry</button>
            </div>
          </div>
        ) : !finding || !audit ? (
          <div className="audit-panel qa-finding-detail__state">
            <Link2 size={20} />
            <div>
              <strong>Finding not linked</strong>
              <p>This finding does not exist in the current AMO, or it is no longer linked to an active audit.</p>
            </div>
          </div>
        ) : (
          <>
            <FindingCaseView finding={finding} car={car} amoCode={amoCode}/>
          </>
        )}
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityFindingDetailPage;

