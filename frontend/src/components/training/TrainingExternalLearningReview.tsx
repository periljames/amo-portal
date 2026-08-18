import React, { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { listTrainingCourses } from "../../services/training";
import {
  listExternalLearningReviewQueue,
  reviewExternalLearning,
  type ExternalLearningReviewItem,
} from "../../services/trainingExternalReview";

const human = (value: unknown) => String(value || "UNKNOWN").replaceAll("_", " ");
const text = (row: Record<string, unknown>, key: string) => String(row[key] || "");

type Props = { canManage: boolean };

const TrainingExternalLearningReview: React.FC<Props> = ({ canManage }) => {
  const client = useQueryClient();
  const queue = useQuery({ queryKey: ["training", "external-learning-review"], queryFn: listExternalLearningReviewQueue, enabled: canManage });
  const courses = useQuery({ queryKey: ["training", "course-catalogue"], queryFn: () => listTrainingCourses({ limit: 500 }), enabled: canManage });
  const [comments, setComments] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const courseById = useMemo(() => new Map((courses.data || []).map((course) => [course.id, course])), [courses.data]);

  if (!canManage) return null;

  const act = async (row: ExternalLearningReviewItem, action: "APPROVE" | "RETURN" | "REJECT" | "VERIFY_COMPLETION") => {
    const comment = (comments[row.id] || "").trim();
    if (!comment) {
      setError("A controlled reviewer comment is required for external-learning decisions.");
      return;
    }
    setBusy(`${row.id}:${action}`);
    setError(null);
    try {
      await reviewExternalLearning(row.id, action, comment);
      setComments((current) => ({ ...current, [row.id]: "" }));
      await client.invalidateQueries({ queryKey: ["training", "external-learning-review"] });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "External-learning review failed.");
    } finally {
      setBusy(null);
    }
  };

  const actionable = (queue.data || []).filter((row) => !["COMPLETED", "REJECTED", "CANCELLED"].includes(row.status));
  return <section className="tos-card">
    <div className="tos-card__heading"><div><h2>External learning approvals</h2><p>Approve or return requests, then independently verify completion only after its evidence has been accepted.</p></div><button onClick={() => void queue.refetch()}>Refresh</button></div>
    {error ? <div className="tos-banner tos-banner--error">{error}<button onClick={() => setError(null)}>×</button></div> : null}
    {queue.isError ? <div className="tos-empty"><strong>External-learning queue unavailable</strong><span>The review state is Unknown, not empty.</span></div> : null}
    {!queue.isLoading && !queue.isError && !actionable.length ? <div className="tos-empty"><strong>No external-learning actions</strong><span>No request or completion is currently awaiting Training review.</span></div> : null}
    <div className="tos-list">{actionable.map((row) => {
      const data = row.data || {};
      const course = row.course_id ? courseById.get(row.course_id) : undefined;
      const returnStage = text(data, "return_stage");
      const evidenceIds = Array.isArray(data.evidence_file_ids) ? data.evidence_file_ids.map(String) : [];
      return <div key={row.id} style={{ alignItems: "flex-start" }}>
        <div style={{ minWidth: 0 }}>
          <strong>{course?.course_name || text(data, "provider_name") || "External learning request"}</strong>
          <small>{human(row.status)} · Provider: {text(data, "provider_name") || "—"} · Planned {text(data, "planned_start") || "—"}</small>
          {row.status === "COMPLETION_SUBMITTED" ? <small>Completion: {text(data, "completion_date") || "—"} · Evidence files: {evidenceIds.length}</small> : null}
          {row.status === "RETURNED" ? <small>Returned stage: {returnStage || "REQUEST"} · {text(data, "return_comment")}</small> : null}
          <textarea rows={2} placeholder="Required review comment" value={comments[row.id] || ""} onChange={(event) => setComments((current) => ({ ...current, [row.id]: event.target.value }))} />
        </div>
        <div className="tos-actions">
          {row.status === "SUBMITTED" ? <><button disabled={Boolean(busy)} onClick={() => void act(row, "RETURN")}>Return</button><button disabled={Boolean(busy)} onClick={() => void act(row, "REJECT")}>Reject</button><button className="primary-chip-btn" disabled={Boolean(busy)} onClick={() => void act(row, "APPROVE")}>Approve</button></> : null}
          {row.status === "COMPLETION_SUBMITTED" ? <><button disabled={Boolean(busy)} onClick={() => void act(row, "RETURN")}>Return evidence</button><button disabled={Boolean(busy)} onClick={() => void act(row, "REJECT")}>Reject</button><button className="primary-chip-btn" disabled={Boolean(busy)} onClick={() => void act(row, "VERIFY_COMPLETION")}>Verify completion</button></> : null}
          {row.status === "APPROVED" ? <span>Awaiting learner completion evidence</span> : null}
          {row.status === "RETURNED" ? <span>Awaiting learner correction</span> : null}
        </div>
      </div>;
    })}</div>
  </section>;
};

export default TrainingExternalLearningReview;
