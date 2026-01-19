import React, { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import AuthLayout from "../components/Layout/AuthLayout";
import {
  qmsGetCarInviteByToken,
  qmsSubmitCarInvite,
  type CARPriority,
  type CARStatus,
} from "../services/qms";

type LoadState = "idle" | "loading" | "ready" | "error" | "submitted";

const PRIORITY_LABELS: Record<CARPriority, string> = {
  LOW: "Low",
  MEDIUM: "Medium",
  HIGH: "High",
  CRITICAL: "Critical",
};

const STATUS_LABELS: Record<CARStatus, string> = {
  DRAFT: "Draft",
  OPEN: "Open",
  IN_PROGRESS: "In progress",
  PENDING_VERIFICATION: "Pending verification",
  CLOSED: "Closed",
  ESCALATED: "Escalated",
  CANCELLED: "Cancelled",
};

const PublicCarInvitePage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");

  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [invite, setInvite] = useState<{
    car_number: string;
    title: string;
    summary: string;
    priority: CARPriority;
    status: CARStatus;
    due_date: string | null;
    target_closure_date: string | null;
  } | null>(null);

  const [form, setForm] = useState({
    submitted_by_name: "",
    submitted_by_email: "",
    containment_action: "",
    root_cause: "",
    corrective_action: "",
    preventive_action: "",
    evidence_ref: "",
    due_date: "",
    target_closure_date: "",
  });

  useEffect(() => {
    const load = async () => {
      if (!token) {
        setError("Invite token missing.");
        setState("error");
        return;
      }
      setState("loading");
      setError(null);
      try {
        const data = await qmsGetCarInviteByToken(token);
        setInvite(data);
        setState("ready");
      } catch (e: any) {
        setError(e?.message || "Failed to load CAR invite.");
        setState("error");
      }
    };
    load();
  }, [token]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!token) return;
    setError(null);
    try {
      await qmsSubmitCarInvite(token, {
        submitted_by_name: form.submitted_by_name.trim(),
        submitted_by_email: form.submitted_by_email.trim(),
        containment_action: form.containment_action.trim(),
        root_cause: form.root_cause.trim(),
        corrective_action: form.corrective_action.trim(),
        preventive_action: form.preventive_action.trim(),
        evidence_ref: form.evidence_ref.trim(),
        due_date: form.due_date || null,
        target_closure_date: form.target_closure_date || null,
      });
      setState("submitted");
    } catch (e: any) {
      setError(e?.message || "Failed to submit CAR response.");
    }
  };

  return (
    <AuthLayout
      title="Corrective Action Response"
      subtitle="Submit your CAR response and evidence. Quality will be notified instantly."
    >
      {state === "loading" && <p>Loading invite…</p>}

      {state === "error" && <p className="text-muted">{error}</p>}

      {state === "submitted" && (
        <div className="card card--success">
          <p>Thank you. Your CAR response has been sent to the Quality team.</p>
        </div>
      )}

      {state === "ready" && invite && (
        <>
          <div className="card" style={{ marginBottom: 16 }}>
            <h2 style={{ marginTop: 0 }}>{invite.title}</h2>
            <p className="text-muted">{invite.summary}</p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <span className="badge badge--neutral">CAR #{invite.car_number}</span>
              <span className="badge badge--info">
                Priority: {PRIORITY_LABELS[invite.priority]}
              </span>
              <span className="badge badge--warning">
                Status: {STATUS_LABELS[invite.status]}
              </span>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="form-grid">
            <label className="form-control">
              <span>Your name</span>
              <input
                type="text"
                value={form.submitted_by_name}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, submitted_by_name: e.target.value }))
                }
                required
              />
            </label>

            <label className="form-control">
              <span>Your email</span>
              <input
                type="email"
                value={form.submitted_by_email}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, submitted_by_email: e.target.value }))
                }
                required
              />
            </label>

            <label className="form-control" style={{ gridColumn: "1 / 3" }}>
              <span>Containment action</span>
              <textarea
                value={form.containment_action}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, containment_action: e.target.value }))
                }
                rows={3}
              />
            </label>

            <label className="form-control" style={{ gridColumn: "1 / 3" }}>
              <span>Root cause</span>
              <textarea
                value={form.root_cause}
                onChange={(e) => setForm((prev) => ({ ...prev, root_cause: e.target.value }))}
                rows={3}
              />
            </label>

            <label className="form-control" style={{ gridColumn: "1 / 3" }}>
              <span>Corrective action</span>
              <textarea
                value={form.corrective_action}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, corrective_action: e.target.value }))
                }
                rows={3}
                required
              />
            </label>

            <label className="form-control" style={{ gridColumn: "1 / 3" }}>
              <span>Preventive action</span>
              <textarea
                value={form.preventive_action}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, preventive_action: e.target.value }))
                }
                rows={3}
              />
            </label>

            <label className="form-control" style={{ gridColumn: "1 / 3" }}>
              <span>Evidence / reference</span>
              <input
                type="text"
                value={form.evidence_ref}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, evidence_ref: e.target.value }))
                }
                placeholder="File reference, link, or document ID"
              />
            </label>

            <label className="form-control">
              <span>Proposed due date</span>
              <input
                type="date"
                value={form.due_date}
                onChange={(e) => setForm((prev) => ({ ...prev, due_date: e.target.value }))}
              />
            </label>

            <label className="form-control">
              <span>Target closure date</span>
              <input
                type="date"
                value={form.target_closure_date}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, target_closure_date: e.target.value }))
                }
              />
            </label>

            <div>
              <button type="submit" className="primary-chip-btn">
                Submit CAR response
              </button>
            </div>
          </form>
        </>
      )}
    </AuthLayout>
  );
};

export default PublicCarInvitePage;
