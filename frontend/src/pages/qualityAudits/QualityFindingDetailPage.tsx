import React from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, CheckCircle2, Link2 } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { hasQmsRolePermission } from "../../app/routeGuards";
import { getContext } from "../../services/auth";
import { ApiClientError } from "../../services/apiClient";
import { qmsGetAuditRegisterPage } from "../../services/qmsRegisters";
import { auditNavigationHref } from "./auditNavigation";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";
import {
  findingLifecycleLabel,
  findingLifecycleView,
  findingNextAction,
  primaryLinkedCar,
} from "./findingLifecycle";

function display(value?: string | null): string {
  return value?.trim() || "Not recorded";
}

const QualityFindingDetailPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string; findingId?: string }>();
  const navigate = useNavigate();
  const context = getContext();
  const amoCode = params.amoCode ?? context.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const findingId = params.findingId?.trim() || "";

  const detailQuery = useQuery({
    queryKey: ["qms-finding-detail", amoCode, findingId],
    queryFn: ({ signal }) => qmsGetAuditRegisterPage({
      findingId,
      limit: 1,
      offset: 0,
      signal,
    }),
    enabled: Boolean(findingId),
    staleTime: 15_000,
    retry: (failureCount, error) => !(error instanceof ApiClientError && [401, 403, 404].includes(error.status)) && failureCount < 1,
  });

  const row = detailQuery.data?.rows[0];
  const finding = row?.finding;
  const audit = row?.audit;
  const linkedCars = row?.linked_cars ?? [];
  const car = primaryLinkedCar(linkedCars);
  const stage = finding ? findingLifecycleView(finding, linkedCars) : null;
  const stageLabel = stage ? findingLifecycleLabel(stage) : undefined;
  const unauthorized = detailQuery.error instanceof ApiClientError
    && [401, 403].includes(detailQuery.error.status);
  const canCreateCar = hasQmsRolePermission("qms.car.create");

  return (
    <QualityAuditsSectionLayout
      title={finding?.finding_ref || "Finding detail"}
      subtitle="Finding context and its governed corrective-action handoff."
    >
      <div className="audit-workspace qa-finding-detail">
        <button
          type="button"
          className="qa-finding-detail__back"
          onClick={() => navigate(`/maintenance/${amoCode}/quality/audits/register?tab=findings`)}
        >
          <ArrowLeft size={15} /> Findings & Actions
        </button>

        {detailQuery.isLoading ? (
          <div className="audit-panel qa-finding-detail__state" role="status">Loading finding…</div>
        ) : unauthorized ? (
          <div className="audit-panel qa-finding-detail__state" role="alert">
            <AlertTriangle size={20} />
            <div><strong>Not authorized</strong><p>You do not have access to this finding.</p></div>
          </div>
        ) : detailQuery.isError ? (
          <div className="audit-panel qa-finding-detail__state" role="alert">
            <AlertTriangle size={20} />
            <div>
              <strong>Finding could not be loaded</strong>
              <p>
                {/uuid_parsing|valid UUID/i.test(detailQuery.error instanceof Error ? detailQuery.error.message : "")
                  ? "This finding link is invalid. Open Findings & Actions and select a finding from the register."
                  : detailQuery.error instanceof Error
                    ? detailQuery.error.message
                    : "The request failed."}
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
            <section className="audit-panel qa-finding-detail__hero">
              <div>
                <div className="audit-chip-list">
                  <span className={`qms-pill${stage !== "closed" ? " qms-pill--warn" : ""}`}>{stageLabel}</span>
                  <span className="qms-pill">{finding.severity || finding.level}</span>
                  <span className="qms-pill">{finding.finding_type.replaceAll("_", " ")}</span>
                </div>
                <h2>{finding.finding_ref || finding.id}</h2>
                <p>{finding.description}</p>
              </div>
              <div className="qa-finding-detail__primary">
                {car ? (
                  <button
                    type="button"
                    className="btn btn--primary"
                    onClick={() => navigate(`/maintenance/${amoCode}/quality/cars?carId=${encodeURIComponent(car.id)}`)}
                  >
                    Continue corrective action
                  </button>
                ) : canCreateCar ? (
                  <button
                    type="button"
                    className="btn btn--primary"
                    onClick={() => navigate(`/maintenance/${amoCode}/quality/cars/new?findingId=${encodeURIComponent(finding.id)}`)}
                  >
                    Create corrective action
                  </button>
                ) : (
                  <span className="text-muted">Corrective-action creation is not available for your role.</span>
                )}
              </div>
            </section>

            <section className="qa-finding-detail__grid" aria-label="Finding details">
              <div className="audit-panel">
                <h3>Finding context</h3>
                <dl>
                  <div><dt>Severity</dt><dd>{display(finding.severity || finding.level)}</dd></div>
                  <div><dt>Requirement</dt><dd>{display(finding.requirement_ref)}</dd></div>
                  <div><dt>Objective evidence / context</dt><dd>{display(finding.objective_evidence || audit.scope || audit.criteria)}</dd></div>
                  <div><dt>Owner</dt><dd>{display(finding.acknowledged_by_name || finding.acknowledged_by_email)}</dd></div>
                  <div><dt>Due</dt><dd>{display(finding.target_close_date || car?.target_closure_date || car?.due_date)}</dd></div>
                </dl>
              </div>
              <div className="audit-panel">
                <h3>Lifecycle</h3>
                <dl>
                  <div>
                    <dt>Audit</dt>
                    <dd>
                      <button
                        type="button"
                        className="qa-register-audit-link"
                        onClick={() => navigate(auditNavigationHref(amoCode, audit))}
                      >
                        {audit.audit_ref}
                      </button>
                      <span>{audit.title}</span>
                    </dd>
                  </div>
                  <div><dt>Linked CAR</dt><dd>{car ? `${car.car_number} · ${car.title}` : "Not linked"}</dd></div>
                  <div><dt>Current action stage</dt><dd>{stageLabel}</dd></div>
                  <div><dt>Next action</dt><dd>{stage ? findingNextAction(stage, Boolean(car)) : "Review finding"}</dd></div>
                  <div><dt>State</dt><dd>{stage === "closed" ? <><CheckCircle2 size={15} /> Closed</> : "Open"}</dd></div>
                </dl>
              </div>
            </section>
          </>
        )}
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityFindingDetailPage;

