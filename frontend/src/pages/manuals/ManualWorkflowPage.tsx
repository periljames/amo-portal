import { useEffect, useMemo, useState } from "react";
import {
  getRevisionWorkflow,
  transitionManualLifecycle,
  type ManualWorkflowPayload,
} from "../../services/manuals";
import { useManualRouteContext } from "./context";
import ManualsPageLayout from "./ManualsPageLayout";

const ACTION_LABELS: Record<string, string> = {
  submit_for_review: "Submit for review",
  endorse_am: "Endorse (AM)",
  submit_kcaa: "Submit to KCAA",
  verify_kcaa: "Verify KCAA",
  publish: "Publish live",
  reject_to_draft: "Reject to draft",
  archive: "Archive",
};

export default function ManualWorkflowPage() {
  const { tenant, manualId, revId } = useManualRouteContext();
  const [workflow, setWorkflow] = useState<ManualWorkflowPayload | null>(null);
  const [comment, setComment] = useState("");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string>("");

  const refresh = () => {
    if (!tenant || !manualId || !revId) return;
    getRevisionWorkflow(tenant, manualId, revId).then(setWorkflow).catch(() => setWorkflow(null));
  };

  useEffect(() => {
    refresh();
  }, [tenant, manualId, revId]);

  const availableActions = useMemo(() => workflow?.allowed_actions || [], [workflow]);

  return (
    <ManualsPageLayout title="Workflow Trail" subtitle="Seven-step publication rail with auditable stage history and quick review for sign-off.">
      <section className="manuals-pane">
        <div className="manuals-process-rail">
          {(workflow?.process_rail || []).map((step) => (
            <button
              key={step.key}
              type="button"
              className={`manuals-process-step manuals-process-step--${step.state}`}
              title={step.at || step.label}
            >
              <span className="manuals-process-step__label">{step.label}</span>
              <span className="manuals-process-step__state">{step.state}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="manuals-shell-grid manuals-shell-grid--workflow">
        <section className="manuals-pane">
          <div className="manuals-pane__header">
            <div>
              <strong>Current stage</strong>
              <p className="manuals-muted">{workflow?.current_stage || "Unavailable"}</p>
            </div>
            <div className="manuals-summary-card manuals-summary-card--compact">
              <span>KCAA ref</span>
              <strong>{workflow?.authority_approval_ref || "Pending"}</strong>
            </div>
          </div>

          <div className="manuals-pcr-form">
            <label className="manuals-stack-field">
              <span>Workflow comment</span>
              <textarea
                className="manuals-search"
                rows={4}
                placeholder="Capture review notes, endorsement remarks, or KCAA reference context."
                value={comment}
                onChange={(event) => setComment(event.target.value)}
              />
            </label>

            <div className="manuals-header-actions">
              {availableActions.map((action) => (
                <button
                  key={action}
                  type="button"
                  className={action === "publish" ? "manuals-primary-btn" : "manuals-link-btn"}
                  disabled={busyAction === action}
                  onClick={async () => {
                    if (!tenant || !manualId || !revId) return;
                    setBusyAction(action);
                    setFeedback("");
                    try {
                      const response = await transitionManualLifecycle(tenant, manualId, revId, action, comment || undefined);
                      setFeedback(`Moved from ${response.previous_state} to ${response.state}.`);
                      setComment("");
                      refresh();
                    } catch (error) {
                      setFeedback(error instanceof Error ? error.message : "Workflow action failed.");
                    } finally {
                      setBusyAction(null);
                    }
                  }}
                >
                  {busyAction === action ? "Working…" : ACTION_LABELS[action] || action}
                </button>
              ))}
            </div>

            {feedback ? <div className="manuals-inline-state manuals-inline-state--muted">{feedback}</div> : null}
          </div>
        </section>

        <section className="manuals-pane">
          <div className="manuals-pane__header">
            <div>
              <strong>Quick review</strong>
              <p className="manuals-muted">One-page change summary for AM endorsement and KCAA transmittal prep.</p>
            </div>
          </div>

          <div className="manuals-summary-grid manuals-summary-grid--2">
            <div className="manuals-summary-card"><span>Changed sections</span><strong>{workflow?.quick_review?.changed_sections ?? 0}</strong></div>
            <div className="manuals-summary-card"><span>Changed blocks</span><strong>{workflow?.quick_review?.changed_blocks ?? 0}</strong></div>
            <div className="manuals-summary-card"><span>Added</span><strong>{workflow?.quick_review?.added ?? 0}</strong></div>
            <div className="manuals-summary-card"><span>Removed</span><strong>{workflow?.quick_review?.removed ?? 0}</strong></div>
          </div>

          <div className="manuals-stack-field">
            <strong>Changed pages / blocks</strong>
            <ul className="manuals-bullet-list">
              {(workflow?.quick_review?.changed_pages || []).map((item) => (
                <li key={item}>{item}</li>
              ))}
              {!(workflow?.quick_review?.changed_pages || []).length ? <li>No indexed change summary yet.</li> : null}
            </ul>
          </div>

          <div className="manuals-stack-field">
            <strong>Change highlights</strong>
            <ul className="manuals-bullet-list">
              {(workflow?.quick_review?.change_highlights || []).map((item, index) => (
                <li key={`${item}-${index}`}>{item}</li>
              ))}
              {!(workflow?.quick_review?.change_highlights || []).length ? <li>No text highlights available.</li> : null}
            </ul>
          </div>
        </section>
      </section>

      <section className="manuals-pane">
        <h2 className="manuals-section-title">Audit history</h2>
        <div className="manuals-history-list">
          {(workflow?.history || []).map((entry, idx) => (
            <article key={`${entry.at}-${idx}`} className="manuals-history-list__item">
              <div>
                <strong>{entry.action}</strong>
                <p>{entry.at}</p>
              </div>
              <span>{entry.actor_id || "system"}</span>
            </article>
          ))}
          {!(workflow?.history || []).length ? <div className="manuals-empty-cell">No workflow history captured yet.</div> : null}
        </div>
      </section>
    </ManualsPageLayout>
  );
}
