import { useCallback, useEffect, useState } from "react";

import {
  downloadTrainingInvitationCalendar,
  listMyTrainingInvitations,
  respondToTrainingInvitation,
  type LearnerTrainingInvitation,
} from "../../services/trainingWorkflowCompletion";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Training invitations could not be loaded.";
}

const TrainingInvitationInbox = () => {
  const [items, setItems] = useState<LearnerTrainingInvitation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await listMyTrainingInvitations(false));
    } catch (err: unknown) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const respond = async (id: string, response: "ACCEPTED" | "DECLINED" | "TENTATIVE") => {
    setSavingId(id);
    setError(null);
    try {
      await respondToTrainingInvitation(id, response);
      await load();
    } catch (err: unknown) {
      setError(errorMessage(err));
    } finally {
      setSavingId(null);
    }
  };

  if (!loading && !error && !items.length) return null;

  return (
    <section className="page-section" id="training-invitations" aria-labelledby="training-invitations-title">
      <div className="card">
        <div className="card-header" style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
          <div>
            <h2 id="training-invitations-title">Training invitations</h2>
            <p className="text-muted">Respond to sessions and add the same governed event to Outlook, Google Calendar or another calendar app.</p>
          </div>
          <button type="button" className="secondary-chip-btn" onClick={() => void load()} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
        {error ? <div className="card card--error"><p>{error}</p></div> : null}
        {loading && !items.length ? <p>Loading invitations…</p> : null}
        <div style={{ display: "grid", gap: 10 }}>
          {items.map((invitation) => (
            <article key={invitation.id} style={{ border: "1px solid #dde4ee", borderRadius: 10, padding: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                <strong>{invitation.event_title || invitation.course_name}</strong>
                <span className="badge badge--neutral">{invitation.rsvp_status.replaceAll("_", " ")}</span>
              </div>
              <div className="text-muted" style={{ marginTop: 4 }}>
                {invitation.course_code ? `${invitation.course_code} · ` : ""}{invitation.course_name}
              </div>
              <div style={{ marginTop: 6 }}>
                {new Date(`${invitation.starts_on}T00:00:00`).toLocaleDateString()}
                {invitation.ends_on && invitation.ends_on !== invitation.starts_on
                  ? ` – ${new Date(`${invitation.ends_on}T00:00:00`).toLocaleDateString()}`
                  : ""}
                {invitation.location ? ` · ${invitation.location}` : ""}
                {invitation.provider ? ` · ${invitation.provider}` : ""}
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
                <button type="button" className="primary-chip-btn" disabled={savingId === invitation.id} onClick={() => void respond(invitation.id, "ACCEPTED")}>
                  Accept
                </button>
                <button type="button" className="secondary-chip-btn" disabled={savingId === invitation.id} onClick={() => void respond(invitation.id, "TENTATIVE")}>
                  Tentative
                </button>
                <button type="button" className="secondary-chip-btn" disabled={savingId === invitation.id} onClick={() => void respond(invitation.id, "DECLINED")}>
                  Decline
                </button>
                <button type="button" className="secondary-chip-btn" onClick={() => void downloadTrainingInvitationCalendar(invitation).catch((err: unknown) => setError(errorMessage(err)))}>
                  Add to calendar
                </button>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
};

export default TrainingInvitationInbox;
