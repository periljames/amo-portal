import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { Button, InlineAlert, PageHeader, Panel, StatusPill } from "../components/UI/Admin";
import { getCachedUser, getContext } from "../services/auth";
import { listEmailLogs, type EmailLog, type EmailLogStatus } from "../services/emailLogs";

type UrlParams = {
  amoCode?: string;
};

const STATUS_OPTIONS: Array<{ value: EmailLogStatus | "ALL"; label: string }> = [
  { value: "ALL", label: "All statuses" },
  { value: "QUEUED", label: "Queued" },
  { value: "SENT", label: "Sent" },
  { value: "FAILED", label: "Failed" },
  { value: "SKIPPED_NO_PROVIDER", label: "Skipped (no provider)" },
];

const statusTone = (status: EmailLogStatus): "healthy" | "degraded" | "down" | "paused" => {
  switch (status) {
    case "SENT":
      return "healthy";
    case "FAILED":
      return "down";
    case "SKIPPED_NO_PROVIDER":
      return "paused";
    case "QUEUED":
    default:
      return "degraded";
  }
};

const formatDate = (value?: string | null): string => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

const EmailLogsPage: React.FC = () => {
  const { amoCode } = useParams<UrlParams>();
  const navigate = useNavigate();
  const ctx = getContext();

  const currentUser = useMemo(() => getCachedUser(), []);
  const isSuperuser = !!currentUser?.is_superuser;
  const isAmoAdmin = !!currentUser?.is_amo_admin;
  const isQualityManager = currentUser?.role === "QUALITY_MANAGER";
  const canAccessAdmin = isSuperuser || isAmoAdmin || isQualityManager;

  const [status, setStatus] = useState<EmailLogStatus | "ALL">("ALL");
  const [templateKey, setTemplateKey] = useState("");
  const [recipient, setRecipient] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");

  const [logs, setLogs] = useState<EmailLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!currentUser) return;
    if (canAccessAdmin) return;

    const dept = ctx.department;
    if (amoCode && dept) {
      navigate(`/maintenance/${amoCode}/${dept}`, { replace: true });
      return;
    }

    if (amoCode) {
      navigate(`/maintenance/${amoCode}/login`, { replace: true });
      return;
    }

    navigate("/login", { replace: true });
  }, [currentUser, canAccessAdmin, amoCode, ctx.department, navigate]);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listEmailLogs({
        status: status === "ALL" ? undefined : status,
        templateKey: templateKey.trim() || undefined,
        recipient: recipient.trim() || undefined,
        start: start || undefined,
        end: end || undefined,
      });
      setLogs(data);
    } catch (err: any) {
      console.error("Failed to load email logs", err);
      setError(err?.message || "Could not load email logs.");
    } finally {
      setLoading(false);
    }
  }, [end, recipient, start, status, templateKey]);

  useEffect(() => {
    if (!canAccessAdmin) return;
    loadLogs();
  }, [canAccessAdmin, loadLogs]);

  const showUnauthorizedBanner = currentUser && !canAccessAdmin;

  return (
    <DepartmentLayout amoCode={amoCode ?? "UNKNOWN"} activeDepartment="admin-email-logs">
      <div className="admin-page">
        <PageHeader
          title="Email Logs"
          subtitle="Immutable outbound email attempts for compliance evidence."
          actions={
            <div className="admin-email-settings__actions">
              {isSuperuser && (
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    navigate(`/maintenance/${amoCode ?? "UNKNOWN"}/admin/email-settings`)
                  }
                >
                  Configure email server
                </Button>
              )}
              <Button type="button" variant="secondary" size="sm" onClick={loadLogs}>
                Refresh
              </Button>
            </div>
          }
        />

        {showUnauthorizedBanner && (
          <InlineAlert tone="warning" title="Access restricted">
            <span>Only admin and QA roles can view email logs.</span>
          </InlineAlert>
        )}

        <Panel title="Filters">
          <div className="admin-table-toolbar">
            <select
              className="input"
              value={status}
              onChange={(event) => setStatus(event.target.value as EmailLogStatus | "ALL")}
            >
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <input
              className="input"
              type="text"
              value={templateKey}
              onChange={(event) => setTemplateKey(event.target.value)}
              placeholder="Template key"
            />
            <input
              className="input"
              type="text"
              value={recipient}
              onChange={(event) => setRecipient(event.target.value)}
              placeholder="Recipient"
            />
            <input
              className="input"
              type="datetime-local"
              value={start}
              onChange={(event) => setStart(event.target.value)}
            />
            <input
              className="input"
              type="datetime-local"
              value={end}
              onChange={(event) => setEnd(event.target.value)}
            />
            <Button type="button" size="sm" onClick={loadLogs} disabled={loading}>
              Apply
            </Button>
          </div>
        </Panel>

        <Panel title="Email activity" className="admin-page__panel">
          {loading && <p>Loading email logs…</p>}
          {error && (
            <InlineAlert tone="danger" title="Error">
              <span>{error}</span>
            </InlineAlert>
          )}

          {!loading && !error && (
            <>
              {logs.length === 0 && <p>No email logs found.</p>}
              {logs.length > 0 && (
                <div className="admin-table-wrapper">
                  <table className="admin-table">
                    <thead>
                      <tr>
                        <th>Status</th>
                        <th>Recipient</th>
                        <th>Subject</th>
                        <th>Template</th>
                        <th>Created</th>
                        <th>Sent</th>
                        <th>Error</th>
                      </tr>
                    </thead>
                    <tbody>
                      {logs.map((log) => (
                        <tr key={log.id}>
                          <td>
                            <StatusPill
                              status={statusTone(log.status)}
                              label={log.status.replace(/_/g, " ")}
                            />
                          </td>
                          <td>{log.recipient}</td>
                          <td>{log.subject}</td>
                          <td>{log.template_key}</td>
                          <td>{formatDate(log.created_at)}</td>
                          <td>{formatDate(log.sent_at)}</td>
                          <td>
                            {log.error ? (
                              <details>
                                <summary>View</summary>
                                <pre>{log.error}</pre>
                              </details>
                            ) : (
                              "—"
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </Panel>
      </div>
    </DepartmentLayout>
  );
};

export default EmailLogsPage;
