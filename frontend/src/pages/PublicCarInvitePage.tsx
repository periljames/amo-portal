import React, { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import AuthLayout from "../components/Layout/AuthLayout";
import {
  qmsListCarInviteAttachments,
  qmsUploadCarInviteAttachment,
  qmsGetCarInviteByToken,
  qmsSubmitCarInvite,
  type CARPriority,
  type CARStatus,
  type CARAttachmentOut,
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

type InviteCard = {
  car_number: string;
  title: string;
  summary: string;
  priority: CARPriority;
  status: CARStatus;
  due_date: string | null;
  target_closure_date: string | null;
};

type InviteForm = {
  submitted_by_name: string;
  submitted_by_email: string;
  containment_action: string;
  root_cause: string;
  corrective_action: string;
  preventive_action: string;
  evidence_ref: string;
  due_date: string;
  target_closure_date: string;
};

type InviteEntry = {
  token: string;
  state: LoadState;
  error: string | null;
  invite: InviteCard | null;
  form: InviteForm;
  consentAccepted: boolean;
  attachments: CARAttachmentOut[];
  attachmentsError: string | null;
  uploading: boolean;
};

type SelectedPreview = {
  token: string;
  attachment: CARAttachmentOut;
  carNumber: string;
};

const emptyForm = (): InviteForm => ({
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

const PublicCarInvitePage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");

  const [entries, setEntries] = useState<InviteEntry[]>([]);
  const [newToken, setNewToken] = useState("");
  const [selectedPreview, setSelectedPreview] = useState<SelectedPreview | null>(null);
  const initialized = useRef(false);
  const hasEvidence = entries.some((entry) => entry.attachments.length > 0);

  const updateEntry = (tokenValue: string, updater: (entry: InviteEntry) => InviteEntry) => {
    setEntries((prev) =>
      prev.map((entry) => (entry.token === tokenValue ? updater(entry) : entry))
    );
  };

  const createEntry = (tokenValue: string): InviteEntry => ({
    token: tokenValue,
    state: "loading",
    error: null,
    invite: null,
    form: emptyForm(),
    consentAccepted: false,
    attachments: [],
    attachmentsError: null,
    uploading: false,
  });

  const loadInvite = async (tokenValue: string) => {
    updateEntry(tokenValue, (entry) => ({ ...entry, state: "loading", error: null }));
    try {
      const data = await qmsGetCarInviteByToken(tokenValue);
      const attachments = await qmsListCarInviteAttachments(tokenValue);
      updateEntry(tokenValue, (entry) => ({
        ...entry,
        invite: data,
        attachments,
        state: "ready",
      }));
    } catch (e: any) {
      updateEntry(tokenValue, (entry) => ({
        ...entry,
        error: e?.message || "Failed to load CAR invite.",
        state: "error",
      }));
    }
  };

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    if (!token) {
      setEntries([
        {
          token: "",
          state: "error",
          error: "Invite token missing.",
          invite: null,
          form: emptyForm(),
          consentAccepted: false,
          attachments: [],
          attachmentsError: null,
          uploading: false,
        },
      ]);
      return;
    }
    const tokens = token
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    const initialEntries = tokens.map((tokenValue) => createEntry(tokenValue));
    setEntries(initialEntries);
    tokens.forEach((tokenValue) => {
      void loadInvite(tokenValue);
    });
  }, [token]);

  useEffect(() => {
    if (!selectedPreview) return;
    const entry = entries.find((item) => item.token === selectedPreview.token);
    const stillExists = entry?.attachments.some(
      (attachment) => attachment.id === selectedPreview.attachment.id
    );
    if (!stillExists) {
      setSelectedPreview(null);
    }
  }, [entries, selectedPreview]);

  const handleSubmit = (tokenValue: string) => async (event: React.FormEvent) => {
    event.preventDefault();
    if (!tokenValue) return;
    const current = entries.find((entry) => entry.token === tokenValue);
    if (!current) return;
    if (!current.consentAccepted) {
      updateEntry(tokenValue, (entry) => ({
        ...entry,
        error: "Please accept the Kenya privacy and policy consent before submitting.",
      }));
      return;
    }
    updateEntry(tokenValue, (entry) => ({ ...entry, error: null }));
    try {
      await qmsSubmitCarInvite(tokenValue, {
        submitted_by_name: current.form.submitted_by_name.trim(),
        submitted_by_email: current.form.submitted_by_email.trim(),
        containment_action: current.form.containment_action.trim(),
        root_cause: current.form.root_cause.trim(),
        corrective_action: current.form.corrective_action.trim(),
        preventive_action: current.form.preventive_action.trim(),
        evidence_ref: current.form.evidence_ref.trim(),
        due_date: current.form.due_date || null,
        target_closure_date: current.form.target_closure_date || null,
      });
      updateEntry(tokenValue, (entry) => ({ ...entry, state: "submitted" }));
    } catch (e: any) {
      updateEntry(tokenValue, (entry) => ({
        ...entry,
        error: e?.message || "Failed to submit CAR response.",
      }));
    }
  };

  const handleUpload = (tokenValue: string) => async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;
    updateEntry(tokenValue, (entry) => ({ ...entry, uploading: true, attachmentsError: null }));
    try {
      const uploads = Array.from(files);
      const results: CARAttachmentOut[] = [];
      for (const upload of uploads) {
        const uploaded = await qmsUploadCarInviteAttachment(tokenValue, upload);
        results.push(uploaded);
      }
      updateEntry(tokenValue, (entry) => ({
        ...entry,
        attachments: [...entry.attachments, ...results],
        uploading: false,
      }));
    } catch (e: any) {
      updateEntry(tokenValue, (entry) => ({
        ...entry,
        uploading: false,
        attachmentsError: e?.message || "Failed to upload attachment.",
      }));
    } finally {
      event.target.value = "";
    }
  };

  const handleAddToken = () => {
    const trimmed = newToken.trim();
    if (!trimmed) return;
    if (entries.some((entry) => entry.token === trimmed)) {
      setNewToken("");
      return;
    }
    setEntries((prev) => [...prev, createEntry(trimmed)]);
    setNewToken("");
    void loadInvite(trimmed);
  };

  return (
    <AuthLayout
      title="Corrective Action Response"
      subtitle="Submit your CAR response and evidence. Quality will be notified instantly."
    >
      <div className="card" style={{ marginBottom: 16 }}>
        <h2 style={{ marginTop: 0 }}>Have multiple findings?</h2>
        <p className="text-muted">
          Add another invite token below to respond to more than one CAR on this page.
        </p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            type="text"
            value={newToken}
            onChange={(e) => setNewToken(e.target.value)}
            placeholder="Paste another invite token"
          />
          <button type="button" className="primary-chip-btn" onClick={handleAddToken}>
            Add CAR
          </button>
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns:
            selectedPreview && hasEvidence
              ? "minmax(0, 1fr) minmax(0, 1fr)"
              : "minmax(0, 1fr)",
          gap: 24,
          alignItems: "start",
        }}
      >
        <div>
          {entries.map((entry) => (
            <div
              key={entry.token || "missing-token"}
              style={{
                marginBottom: 24,
                padding: 20,
                borderRadius: 12,
                border: "1px solid #e5e5e5",
                background: "transparent",
              }}
            >
              {entry.state === "loading" && <p>Loading invite…</p>}

              {entry.state === "error" && <p className="text-muted">{entry.error}</p>}

              {entry.state === "submitted" && (
                <div className="card card--success">
                  <p>Thank you. Your CAR response has been sent to the Quality team.</p>
                </div>
              )}

              {entry.state === "ready" && entry.invite && (
                <>
                  <div style={{ marginBottom: 16 }}>
                    <h2 style={{ marginTop: 0 }}>{entry.invite.title}</h2>
                    <p className="text-muted" style={{ marginBottom: 12 }}>
                      {entry.invite.summary}
                    </p>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <span className="badge badge--neutral">CAR #{entry.invite.car_number}</span>
                      <span className="badge badge--info">
                        Priority: {PRIORITY_LABELS[entry.invite.priority]}
                      </span>
                      <span className="badge badge--warning">
                        Status: {STATUS_LABELS[entry.invite.status]}
                      </span>
                    </div>
                  </div>

                  {entry.error && <p className="text-muted">{entry.error}</p>}

                  <form onSubmit={handleSubmit(entry.token)} className="form-grid">
                    <label className="form-control">
                      <span>Your name</span>
                      <input
                        type="text"
                        value={entry.form.submitted_by_name}
                        onChange={(e) =>
                          updateEntry(entry.token, (prev) => ({
                            ...prev,
                            form: { ...prev.form, submitted_by_name: e.target.value },
                          }))
                        }
                        required
                      />
                    </label>

                    <label className="form-control">
                      <span>Your email</span>
                      <input
                        type="email"
                        value={entry.form.submitted_by_email}
                        onChange={(e) =>
                          updateEntry(entry.token, (prev) => ({
                            ...prev,
                            form: { ...prev.form, submitted_by_email: e.target.value },
                          }))
                        }
                        required
                      />
                    </label>

                    <label className="form-control" style={{ gridColumn: "1 / 3" }}>
                      <span>Containment action</span>
                      <textarea
                        value={entry.form.containment_action}
                        onChange={(e) =>
                          updateEntry(entry.token, (prev) => ({
                            ...prev,
                            form: { ...prev.form, containment_action: e.target.value },
                          }))
                        }
                        rows={3}
                      />
                    </label>

                    <label className="form-control" style={{ gridColumn: "1 / 3" }}>
                      <span>Root cause</span>
                      <textarea
                        value={entry.form.root_cause}
                        onChange={(e) =>
                          updateEntry(entry.token, (prev) => ({
                            ...prev,
                            form: { ...prev.form, root_cause: e.target.value },
                          }))
                        }
                        rows={3}
                      />
                    </label>

                    <label className="form-control" style={{ gridColumn: "1 / 3" }}>
                      <span>Corrective action</span>
                      <textarea
                        value={entry.form.corrective_action}
                        onChange={(e) =>
                          updateEntry(entry.token, (prev) => ({
                            ...prev,
                            form: { ...prev.form, corrective_action: e.target.value },
                          }))
                        }
                        rows={3}
                        required
                      />
                    </label>

                    <label className="form-control" style={{ gridColumn: "1 / 3" }}>
                      <span>Preventive action</span>
                      <textarea
                        value={entry.form.preventive_action}
                        onChange={(e) =>
                          updateEntry(entry.token, (prev) => ({
                            ...prev,
                            form: { ...prev.form, preventive_action: e.target.value },
                          }))
                        }
                        rows={3}
                      />
                    </label>

                    <label className="form-control" style={{ gridColumn: "1 / 3" }}>
                      <span>Evidence / reference</span>
                      <input
                        type="text"
                        value={entry.form.evidence_ref}
                        onChange={(e) =>
                          updateEntry(entry.token, (prev) => ({
                            ...prev,
                            form: { ...prev.form, evidence_ref: e.target.value },
                          }))
                        }
                        placeholder="File reference, link, or document ID"
                      />
                    </label>

                    <label className="form-control" style={{ gridColumn: "1 / 3" }}>
                      <span>Evidence attachments</span>
                      <input
                        type="file"
                        multiple
                        onChange={handleUpload(entry.token)}
                        accept="image/*,.pdf"
                      />
                      {entry.uploading && <span className="text-muted">Uploading...</span>}
                      {entry.attachmentsError && (
                        <span className="text-muted">{entry.attachmentsError}</span>
                      )}
                      {entry.attachments.length > 0 && (
                        <div
                          style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
                            gap: 12,
                            marginTop: 12,
                          }}
                        >
                          {entry.attachments.map((attachment) => {
                            const isImage = attachment.content_type?.startsWith("image/");
                            const isPdf =
                              attachment.content_type?.includes("pdf") ||
                              attachment.filename.toLowerCase().endsWith(".pdf");
                            return (
                              <button
                                key={attachment.id}
                                type="button"
                                onClick={() =>
                                  setSelectedPreview({
                                    token: entry.token,
                                    attachment,
                                    carNumber: entry.invite?.car_number || "",
                                  })
                                }
                                style={{
                                  border: "1px solid #d6d6d6",
                                  borderRadius: 8,
                                  padding: 8,
                                  background: "white",
                                  textAlign: "left",
                                  cursor: "pointer",
                                }}
                              >
                                {isImage && (
                                  <img
                                    src={attachment.download_url}
                                    alt={attachment.filename}
                                    style={{
                                      width: "100%",
                                      height: 120,
                                      objectFit: "cover",
                                      borderRadius: 6,
                                      marginBottom: 8,
                                    }}
                                  />
                                )}
                                {!isImage && isPdf && (
                                  <div
                                    style={{
                                      height: 120,
                                      display: "flex",
                                      alignItems: "center",
                                      justifyContent: "center",
                                      borderRadius: 6,
                                      border: "1px solid #e6e6e6",
                                      marginBottom: 8,
                                      background: "#fafafa",
                                      fontSize: 12,
                                    }}
                                  >
                                    PDF Preview
                                  </div>
                                )}
                                {!isImage && !isPdf && (
                                  <div
                                    style={{
                                      height: 120,
                                      display: "flex",
                                      alignItems: "center",
                                      justifyContent: "center",
                                      background: "#f5f5f5",
                                      borderRadius: 6,
                                      marginBottom: 8,
                                    }}
                                  >
                                    <span>File</span>
                                  </div>
                                )}
                                <div style={{ fontSize: 12, wordBreak: "break-word" }}>
                                  {attachment.filename}
                                </div>
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </label>

                    <label className="form-control">
                      <span>Proposed due date</span>
                      <input
                        type="date"
                        value={entry.form.due_date}
                        onChange={(e) =>
                          updateEntry(entry.token, (prev) => ({
                            ...prev,
                            form: { ...prev.form, due_date: e.target.value },
                          }))
                        }
                      />
                    </label>

                    <label className="form-control">
                      <span>Target closure date</span>
                      <input
                        type="date"
                        value={entry.form.target_closure_date}
                        onChange={(e) =>
                          updateEntry(entry.token, (prev) => ({
                            ...prev,
                            form: { ...prev.form, target_closure_date: e.target.value },
                          }))
                        }
                      />
                    </label>

                    <label className="form-control" style={{ gridColumn: "1 / 3" }}>
                      <span>Consent (Kenya privacy & policy)</span>
                      <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                        <input
                          type="checkbox"
                          checked={entry.consentAccepted}
                          onChange={(e) =>
                            updateEntry(entry.token, (prev) => ({
                              ...prev,
                              consentAccepted: e.target.checked,
                            }))
                          }
                          required
                        />
                        <span>
                          I consent to the applicable Kenya privacy and regulatory policies for
                          submitting this CAR response.
                        </span>
                      </div>
                    </label>

                    <div>
                      <button
                        type="submit"
                        className="primary-chip-btn"
                        disabled={!entry.consentAccepted}
                      >
                        Submit CAR response
                      </button>
                    </div>
                  </form>
                </>
              )}
            </div>
          ))}
        </div>

        {selectedPreview && hasEvidence && (
          <div
            className="card"
            style={{
              position: "sticky",
              top: 16,
              alignSelf: "flex-start",
              borderRadius: 12,
              padding: 16,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <div>
                <h3 style={{ marginTop: 0, marginBottom: 4 }}>Evidence Preview</h3>
                <p className="text-muted" style={{ marginTop: 0 }}>
                  CAR #{selectedPreview.carNumber} • {selectedPreview.attachment.filename}
                </p>
              </div>
              <button
                type="button"
                className="primary-chip-btn"
                onClick={() => setSelectedPreview(null)}
              >
                Close
              </button>
            </div>

            {selectedPreview.attachment.content_type?.startsWith("image/") && (
              <div style={{ marginTop: 12 }}>
                <img
                  src={selectedPreview.attachment.download_url}
                  alt={selectedPreview.attachment.filename}
                  style={{ width: "100%", maxHeight: "70vh", objectFit: "contain" }}
                />
              </div>
            )}

            {selectedPreview.attachment.content_type?.includes("pdf") ||
            selectedPreview.attachment.filename.toLowerCase().endsWith(".pdf") ? (
              <div style={{ marginTop: 12, height: "70vh", border: "1px solid #e6e6e6" }}>
                <embed
                  src={selectedPreview.attachment.download_url}
                  type="application/pdf"
                  style={{ width: "100%", height: "100%" }}
                />
              </div>
            ) : null}

            {!selectedPreview.attachment.content_type?.startsWith("image/") &&
              !(
                selectedPreview.attachment.content_type?.includes("pdf") ||
                selectedPreview.attachment.filename.toLowerCase().endsWith(".pdf")
              ) && (
                <div style={{ marginTop: 12 }}>
                  <a href={selectedPreview.attachment.download_url} target="_blank" rel="noreferrer">
                    Download {selectedPreview.attachment.filename}
                  </a>
                </div>
              )}
          </div>
        )}
      </div>
    </AuthLayout>
  );
};

export default PublicCarInvitePage;
