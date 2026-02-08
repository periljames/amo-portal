import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { Button, InlineAlert, PageHeader, Panel, StatusPill } from "../components/UI/Admin";
import { getCachedUser, getContext } from "../services/auth";
import "../styles/emailServerSettings.css";
import {
  clearEmailServerConfig,
  defaultEmailServerConfig,
  loadEmailServerConfig,
  saveEmailServerConfig,
  type EmailProvider,
  type EmailServerConfig,
} from "../services/emailServerConfig";

type UrlParams = {
  amoCode?: string;
};

type TestState = "idle" | "running" | "success" | "error";

type HelpTopicKey = "smtp" | "test-console" | "compatibility" | "general";

type HelpTopic = {
  title: string;
  body: React.ReactNode;
};

const PROVIDER_LABELS: Record<EmailProvider, string> = {
  none: "No provider (logging only)",
  smtp: "SMTP (own mail server)",
  sendgrid: "SendGrid",
  ses: "Amazon SES",
  mailgun: "Mailgun",
  postmark: "Postmark",
  custom_http: "Custom HTTP API",
};

const EmailServerSettingsPage: React.FC = () => {
  const { amoCode } = useParams<UrlParams>();
  const navigate = useNavigate();
  const ctx = getContext();

  const currentUser = useMemo(() => getCachedUser(), []);
  const isSuperuser = !!currentUser?.is_superuser;

  const [config, setConfig] = useState<EmailServerConfig>(() =>
    loadEmailServerConfig()
  );
  const [autoSave, setAutoSave] = useState(true);
  const [autoTest, setAutoTest] = useState(true);
  const [includeSecrets, setIncludeSecrets] = useState(false);
  const [testState, setTestState] = useState<TestState>("idle");
  const [testMessage, setTestMessage] = useState<string | null>(null);
  const [testLatencyMs, setTestLatencyMs] = useState<number | null>(null);
  const [testPayloadBytes, setTestPayloadBytes] = useState<number | null>(null);
  const [lastTestedAt, setLastTestedAt] = useState<string | null>(null);
  const [nextTestAt, setNextTestAt] = useState<string | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [helpTopicKey, setHelpTopicKey] = useState<HelpTopicKey>("general");
  const testTimerRef = useRef<number | null>(null);
  const testIntervalRef = useRef<number | null>(null);

  useEffect(() => {
    if (!currentUser) return;
    if (isSuperuser) return;

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
  }, [currentUser, isSuperuser, amoCode, ctx.department, navigate]);

  useEffect(() => {
    if (!autoSave) return;
    saveEmailServerConfig(config);
  }, [autoSave, config]);

  const updateConfig = useCallback(
    (updater: (prev: EmailServerConfig) => EmailServerConfig) => {
      setConfig((prev) => updater(prev));
    },
    []
  );

  const missingFields = useMemo(() => {
    const missing: string[] = [];
    if (!config.fromName.trim()) missing.push("From name");
    if (!config.fromEmail.trim()) missing.push("From email");

    switch (config.provider) {
      case "smtp":
        if (!config.smtp.host.trim()) missing.push("SMTP host");
        if (!config.smtp.port) missing.push("SMTP port");
        if (!config.smtp.username.trim()) missing.push("SMTP username");
        if (!config.smtp.password.trim()) missing.push("SMTP password");
        break;
      case "sendgrid":
        if (!config.sendgrid.apiKey.trim()) missing.push("SendGrid API key");
        break;
      case "ses":
        if (!config.ses.accessKeyId.trim()) missing.push("SES access key");
        if (!config.ses.secretAccessKey.trim()) missing.push("SES secret");
        if (!config.ses.region.trim()) missing.push("SES region");
        break;
      case "mailgun":
        if (!config.mailgun.apiKey.trim()) missing.push("Mailgun API key");
        if (!config.mailgun.domain.trim()) missing.push("Mailgun domain");
        break;
      case "postmark":
        if (!config.postmark.serverToken.trim()) missing.push("Postmark token");
        break;
      case "custom_http":
        if (!config.customHttp.baseUrl.trim()) missing.push("Custom API base URL");
        break;
      default:
        break;
    }
    return missing;
  }, [config]);

  const readinessTone = missingFields.length === 0 ? "healthy" : "degraded";

  const buildTestPayload = (cfg: EmailServerConfig) => {
    if (includeSecrets) return cfg;
    return {
      ...cfg,
      smtp: { ...cfg.smtp, password: cfg.smtp.password ? "********" : "" },
      sendgrid: {
        ...cfg.sendgrid,
        apiKey: cfg.sendgrid.apiKey ? "********" : "",
      },
      ses: {
        ...cfg.ses,
        secretAccessKey: cfg.ses.secretAccessKey ? "********" : "",
      },
      mailgun: {
        ...cfg.mailgun,
        apiKey: cfg.mailgun.apiKey ? "********" : "",
      },
      postmark: {
        ...cfg.postmark,
        serverToken: cfg.postmark.serverToken ? "********" : "",
      },
      customHttp: {
        ...cfg.customHttp,
        authToken: cfg.customHttp.authToken ? "********" : "",
        password: cfg.customHttp.password ? "********" : "",
        headerValue: cfg.customHttp.headerValue ? "********" : "",
      },
    };
  };

  const runConnectionTest = useCallback(async () => {
    if (!config.testEndpointUrl.trim()) {
      setTestState("error");
      setTestMessage(
        "Add a test endpoint URL to run a live check from the browser."
      );
      setTestLatencyMs(null);
      return;
    }
    if (missingFields.length > 0) {
      setTestState("error");
      setTestMessage(`Missing: ${missingFields.join(", ")}`);
      setTestLatencyMs(null);
      return;
    }
    setTestState("running");
    setTestMessage(null);
    setTestLatencyMs(null);
    setTestPayloadBytes(null);
    const controller = new AbortController();
    const startedAt = performance.now();
    const timeout = window.setTimeout(() => controller.abort(), config.testTimeoutMs);
    const payload = {
      provider: config.provider,
      sandbox: config.sandboxMode,
      payload: buildTestPayload(config),
    };
    const serialized = JSON.stringify(payload);
    setTestPayloadBytes(new Blob([serialized]).size);
    try {
      const response = await fetch(config.testEndpointUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: serialized,
        signal: controller.signal,
      });
      const latency = Math.round(performance.now() - startedAt);
      setTestLatencyMs(latency);
      if (!response.ok) {
        const text = await response.text();
        setTestState("error");
        setTestMessage(text || `Test failed with status ${response.status}.`);
        return;
      }
      setTestState("success");
      setTestMessage("Connection test succeeded.");
    } catch (err: any) {
      setTestState("error");
      if (err?.name === "AbortError") {
        setTestMessage("Test timed out. Check connectivity or endpoint uptime.");
      } else {
        setTestMessage(err?.message || "Test failed to complete.");
      }
    } finally {
      window.clearTimeout(timeout);
      setLastTestedAt(new Date().toISOString());
    }
  }, [config, missingFields]);

  useEffect(() => {
    if (!autoTest) return;
    if (!config.testEndpointUrl.trim()) return;
    if (testTimerRef.current) window.clearTimeout(testTimerRef.current);
    testTimerRef.current = window.setTimeout(() => {
      runConnectionTest();
    }, 900);
    return () => {
      if (testTimerRef.current) window.clearTimeout(testTimerRef.current);
    };
  }, [autoTest, config, runConnectionTest]);

  useEffect(() => {
    if (!autoTest) return;
    if (!config.testEndpointUrl.trim()) return;
    if (testIntervalRef.current) window.clearInterval(testIntervalRef.current);
    const scheduleNext = () => {
      const next = new Date(Date.now() + 5 * 60 * 1000);
      setNextTestAt(next.toISOString());
    };
    scheduleNext();
    testIntervalRef.current = window.setInterval(() => {
      runConnectionTest();
      scheduleNext();
    }, 5 * 60 * 1000);
    return () => {
      if (testIntervalRef.current) window.clearInterval(testIntervalRef.current);
    };
  }, [autoTest, config.testEndpointUrl, runConnectionTest]);

  const renderTime = (value: string | null): string => {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
  };

  const renderSpeed = (bytes: number | null, latencyMs: number | null): string => {
    if (!bytes || !latencyMs || latencyMs <= 0) return "—";
    const kilobits = (bytes * 8) / 1024;
    const seconds = latencyMs / 1000;
    const kbps = kilobits / seconds;
    return `${kbps.toFixed(1)} kbps`;
  };

  const resetConfig = () => {
    clearEmailServerConfig();
    setConfig(defaultEmailServerConfig);
    setTestState("idle");
    setTestMessage(null);
    setTestLatencyMs(null);
  };

  const helpTopics: Record<HelpTopicKey, HelpTopic> = {
    general: {
      title: "Operator notes",
      body: (
        <ul className="admin-email-settings__list">
          <li>Settings are stored locally in your browser profile.</li>
          <li>Use sandbox mode for dry-run validations before go-live.</li>
          <li>Realtime testing runs from the browser; ensure CORS is enabled.</li>
        </ul>
      ),
    },
    smtp: {
      title: "SMTP notes",
      body: (
        <ul className="admin-email-settings__list">
          <li>Use port 587 for STARTTLS or 465 for SMTPS.</li>
          <li>App passwords are recommended for Gmail/Outlook.</li>
          <li>Self-signed certs are supported if you enable them.</li>
        </ul>
      ),
    },
    "test-console": {
      title: "Realtime test console",
      body: (
        <ul className="admin-email-settings__list">
          <li>Runs every 5 minutes when realtime testing is enabled.</li>
          <li>Provide a HTTPS endpoint that returns 2xx on success.</li>
          <li>Toggle secret masking based on your environment needs.</li>
        </ul>
      ),
    },
    compatibility: {
      title: "Provider compatibility",
      body: (
        <ul className="admin-email-settings__compatibility">
          <li>Outlook / Microsoft 365: use SMTP or a custom relay gateway.</li>
          <li>Gmail / Google Workspace: use SMTP with app password or OAuth relay.</li>
          <li>Proton Mail: use Proton Bridge SMTP credentials.</li>
          <li>Any provider: custom HTTP adapter with your preferred gateway.</li>
        </ul>
      ),
    },
  };

  const openHelp = (key: HelpTopicKey) => {
    setHelpTopicKey(key);
    setHelpOpen(true);
  };

  const activeHelp = helpTopics[helpTopicKey];

  if (currentUser && !isSuperuser) {
    return null;
  }

  return (
    <DepartmentLayout
      amoCode={amoCode ?? "UNKNOWN"}
      activeDepartment="admin-email-settings"
    >
      <div
        className={
          "admin-page admin-email-settings" +
          (helpOpen ? " admin-email-settings--drawer-open" : "")
        }
      >
        <PageHeader
          title="Email Server Control Deck"
          subtitle="Configure outbound email without touching the backend."
          actions={
            <div className="admin-email-settings__actions">
              <Button type="button" variant="secondary" onClick={resetConfig}>
                Reset
              </Button>
              <Button
                type="button"
                onClick={() => saveEmailServerConfig(config)}
              >
                Save now
              </Button>
            </div>
          }
        />

        <div className="admin-email-settings__banner">
          <div>
            <span className="admin-email-settings__label">Connection readiness</span>
            <div className="admin-email-settings__status">
              <StatusPill
                status={readinessTone}
                label={
                  missingFields.length === 0
                    ? "Ready for live traffic"
                    : `${missingFields.length} fields missing`
                }
              />
              {missingFields.length > 0 && (
                <span className="admin-muted">
                  {missingFields.join(", ")}
                </span>
              )}
            </div>
          </div>
          <div className="admin-email-settings__toggles">
            <span
              className={
                "admin-email-settings__notification" +
                (testState === "error" ? " admin-email-settings__notification--error" : "")
              }
            >
              <span className="admin-email-settings__notification-dot" />
              {testState === "running"
                ? "Testing connection"
                : testState === "success"
                  ? "Connection healthy"
                  : testState === "error"
                    ? "Connection issue"
                    : "Waiting for test"}
            </span>
            <label className="admin-email-settings__toggle">
              <input
                type="checkbox"
                checked={autoSave}
                onChange={(event) => setAutoSave(event.target.checked)}
              />
              Auto-save
            </label>
            <label className="admin-email-settings__toggle">
              <input
                type="checkbox"
                checked={autoTest}
                onChange={(event) => setAutoTest(event.target.checked)}
              />
              Realtime test
            </label>
          </div>
        </div>

        <div className="admin-page__grid">
          <div className="admin-page__main">
            <Panel title="Provider profile" className="admin-email-settings__panel">
              <div className="admin-email-settings__panel-note">
                <button
                  type="button"
                  className="admin-email-settings__help-btn"
                  onClick={() => openHelp("general")}
                  aria-label="Operator notes"
                  title="Operator notes"
                >
                  !
                </button>
              </div>
              <div className="admin-email-settings__grid">
                <div>
                  <label className="admin-email-settings__field-label">Profile label</label>
                  <input
                    className="input"
                    value={config.label}
                    onChange={(event) =>
                      updateConfig((prev) => ({ ...prev, label: event.target.value }))
                    }
                  />
                </div>
                <div>
                  <label className="admin-email-settings__field-label">Provider</label>
                  <select
                    className="input"
                    value={config.provider}
                    onChange={(event) =>
                      updateConfig((prev) => ({
                        ...prev,
                        provider: event.target.value as EmailProvider,
                      }))
                    }
                  >
                    {Object.entries(PROVIDER_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="admin-email-settings__field-label">From name</label>
                  <input
                    className="input"
                    value={config.fromName}
                    onChange={(event) =>
                      updateConfig((prev) => ({ ...prev, fromName: event.target.value }))
                    }
                  />
                </div>
                <div>
                  <label className="admin-email-settings__field-label">From email</label>
                  <input
                    className="input"
                    type="email"
                    value={config.fromEmail}
                    onChange={(event) =>
                      updateConfig((prev) => ({ ...prev, fromEmail: event.target.value }))
                    }
                  />
                </div>
                <div>
                  <label className="admin-email-settings__field-label">Reply-to</label>
                  <input
                    className="input"
                    type="email"
                    value={config.replyTo}
                    onChange={(event) =>
                      updateConfig((prev) => ({ ...prev, replyTo: event.target.value }))
                    }
                  />
                </div>
                <div className="admin-email-settings__toggle-row">
                  <label className="admin-email-settings__toggle">
                    <input
                      type="checkbox"
                      checked={config.sandboxMode}
                      onChange={(event) =>
                        updateConfig((prev) => ({ ...prev, sandboxMode: event.target.checked }))
                      }
                    />
                    Sandbox / dry run mode
                  </label>
                </div>
              </div>
            </Panel>

            {config.provider === "smtp" && (
              <Panel
                title="SMTP settings"
                className="admin-email-settings__panel"
                actions={
                  <button
                    type="button"
                    className="admin-email-settings__help-btn"
                    onClick={() => openHelp("smtp")}
                    aria-label="SMTP settings notes"
                    title="SMTP settings notes"
                  >
                    ?
                  </button>
                }
              >
                <div className="admin-email-settings__grid">
                  <div>
                    <label className="admin-email-settings__field-label">SMTP host</label>
                    <input
                      className="input"
                      value={config.smtp.host}
                      onChange={(event) =>
                        updateConfig((prev) => ({
                          ...prev,
                          smtp: { ...prev.smtp, host: event.target.value },
                        }))
                      }
                    />
                  </div>
                  <div>
                    <label className="admin-email-settings__field-label">Port</label>
                    <input
                      className="input"
                      type="number"
                      value={config.smtp.port}
                      onChange={(event) =>
                        updateConfig((prev) => ({
                          ...prev,
                          smtp: { ...prev.smtp, port: Number(event.target.value) },
                        }))
                      }
                    />
                  </div>
                  <div>
                    <label className="admin-email-settings__field-label">Username</label>
                    <input
                      className="input"
                      value={config.smtp.username}
                      onChange={(event) =>
                        updateConfig((prev) => ({
                          ...prev,
                          smtp: { ...prev.smtp, username: event.target.value },
                        }))
                      }
                    />
                  </div>
                  <div>
                    <label className="admin-email-settings__field-label">Password</label>
                    <input
                      className="input"
                      type="password"
                      value={config.smtp.password}
                      onChange={(event) =>
                        updateConfig((prev) => ({
                          ...prev,
                          smtp: { ...prev.smtp, password: event.target.value },
                        }))
                      }
                    />
                  </div>
                  <div className="admin-email-settings__toggle-row">
                    <label className="admin-email-settings__toggle">
                      <input
                        type="checkbox"
                        checked={config.smtp.secure}
                        onChange={(event) =>
                          updateConfig((prev) => ({
                            ...prev,
                            smtp: { ...prev.smtp, secure: event.target.checked },
                          }))
                        }
                      />
                      TLS/SSL required
                    </label>
                    <label className="admin-email-settings__toggle">
                      <input
                        type="checkbox"
                        checked={config.smtp.allowSelfSigned}
                        onChange={(event) =>
                          updateConfig((prev) => ({
                            ...prev,
                            smtp: { ...prev.smtp, allowSelfSigned: event.target.checked },
                          }))
                        }
                      />
                      Allow self-signed certs
                    </label>
                  </div>
                  <div>
                    <label className="admin-email-settings__field-label">Connection timeout (ms)</label>
                    <input
                      className="input"
                      type="number"
                      value={config.smtp.connectionTimeoutMs}
                      onChange={(event) =>
                        updateConfig((prev) => ({
                          ...prev,
                          smtp: {
                            ...prev.smtp,
                            connectionTimeoutMs: Number(event.target.value),
                          },
                        }))
                      }
                    />
                  </div>
                </div>
                <p className="admin-email-settings__hint">
                  SMTP connections cannot be opened directly from the browser. Use a test
                  endpoint URL below to validate connectivity in real time.
                </p>
              </Panel>
            )}

            {config.provider === "sendgrid" && (
              <Panel title="SendGrid settings" className="admin-email-settings__panel">
                <div className="admin-email-settings__grid">
                  <div>
                    <label className="admin-email-settings__field-label">API key</label>
                    <input
                      className="input"
                      type="password"
                      value={config.sendgrid.apiKey}
                      onChange={(event) =>
                        updateConfig((prev) => ({
                          ...prev,
                          sendgrid: { ...prev.sendgrid, apiKey: event.target.value },
                        }))
                      }
                    />
                  </div>
                  <div>
                    <label className="admin-email-settings__field-label">Subuser</label>
                    <input
                      className="input"
                      value={config.sendgrid.subaccount}
                      onChange={(event) =>
                        updateConfig((prev) => ({
                          ...prev,
                          sendgrid: { ...prev.sendgrid, subaccount: event.target.value },
                        }))
                      }
                    />
                  </div>
                  <div>
                    <label className="admin-email-settings__field-label">IP pool</label>
                    <input
                      className="input"
                      value={config.sendgrid.ipPool}
                      onChange={(event) =>
                        updateConfig((prev) => ({
                          ...prev,
                          sendgrid: { ...prev.sendgrid, ipPool: event.target.value },
                        }))
                      }
                    />
                  </div>
                </div>
              </Panel>
            )}

            {config.provider === "ses" && (
              <Panel title="Amazon SES settings" className="admin-email-settings__panel">
                <div className="admin-email-settings__grid">
                  <div>
                    <label className="admin-email-settings__field-label">Access key ID</label>
                    <input
                      className="input"
                      value={config.ses.accessKeyId}
                      onChange={(event) =>
                        updateConfig((prev) => ({
                          ...prev,
                          ses: { ...prev.ses, accessKeyId: event.target.value },
                        }))
                      }
                    />
                  </div>
                  <div>
                    <label className="admin-email-settings__field-label">Secret access key</label>
                    <input
                      className="input"
                      type="password"
                      value={config.ses.secretAccessKey}
                      onChange={(event) =>
                        updateConfig((prev) => ({
                          ...prev,
                          ses: { ...prev.ses, secretAccessKey: event.target.value },
                        }))
                      }
                    />
                  </div>
                  <div>
                    <label className="admin-email-settings__field-label">Region</label>
                    <input
                      className="input"
                      value={config.ses.region}
                      onChange={(event) =>
                        updateConfig((prev) => ({
                          ...prev,
                          ses: { ...prev.ses, region: event.target.value },
                        }))
                      }
                    />
                  </div>
                  <div>
                    <label className="admin-email-settings__field-label">Configuration set</label>
                    <input
                      className="input"
                      value={config.ses.configurationSet}
                      onChange={(event) =>
                        updateConfig((prev) => ({
                          ...prev,
                          ses: { ...prev.ses, configurationSet: event.target.value },
                        }))
                      }
                    />
                  </div>
                </div>
              </Panel>
            )}

            {config.provider === "mailgun" && (
              <Panel title="Mailgun settings" className="admin-email-settings__panel">
                <div className="admin-email-settings__grid">
                  <div>
                    <label className="admin-email-settings__field-label">API key</label>
                    <input
                      className="input"
                      type="password"
                      value={config.mailgun.apiKey}
                      onChange={(event) =>
                        updateConfig((prev) => ({
                          ...prev,
                          mailgun: { ...prev.mailgun, apiKey: event.target.value },
                        }))
                      }
                    />
                  </div>
                  <div>
                    <label className="admin-email-settings__field-label">Domain</label>
                    <input
                      className="input"
                      value={config.mailgun.domain}
                      onChange={(event) =>
                        updateConfig((prev) => ({
                          ...prev,
                          mailgun: { ...prev.mailgun, domain: event.target.value },
                        }))
                      }
                    />
                  </div>
                  <div>
                    <label className="admin-email-settings__field-label">Region</label>
                    <select
                      className="input"
                      value={config.mailgun.region}
                      onChange={(event) =>
                        updateConfig((prev) => ({
                          ...prev,
                          mailgun: {
                            ...prev.mailgun,
                            region: event.target.value as "us" | "eu",
                          },
                        }))
                      }
                    >
                      <option value="us">US</option>
                      <option value="eu">EU</option>
                    </select>
                  </div>
                </div>
              </Panel>
            )}

            {config.provider === "postmark" && (
              <Panel title="Postmark settings" className="admin-email-settings__panel">
                <div className="admin-email-settings__grid">
                  <div>
                    <label className="admin-email-settings__field-label">Server token</label>
                    <input
                      className="input"
                      type="password"
                      value={config.postmark.serverToken}
                      onChange={(event) =>
                        updateConfig((prev) => ({
                          ...prev,
                          postmark: { ...prev.postmark, serverToken: event.target.value },
                        }))
                      }
                    />
                  </div>
                  <div>
                    <label className="admin-email-settings__field-label">Message stream</label>
                    <input
                      className="input"
                      value={config.postmark.messageStream}
                      onChange={(event) =>
                        updateConfig((prev) => ({
                          ...prev,
                          postmark: { ...prev.postmark, messageStream: event.target.value },
                        }))
                      }
                    />
                  </div>
                </div>
              </Panel>
            )}

            {config.provider === "custom_http" && (
              <Panel title="Custom HTTP settings" className="admin-email-settings__panel">
                <div className="admin-email-settings__grid">
                  <div>
                    <label className="admin-email-settings__field-label">Base URL</label>
                    <input
                      className="input"
                      value={config.customHttp.baseUrl}
                      onChange={(event) =>
                        updateConfig((prev) => ({
                          ...prev,
                          customHttp: { ...prev.customHttp, baseUrl: event.target.value },
                        }))
                      }
                    />
                  </div>
                  <div>
                    <label className="admin-email-settings__field-label">Auth scheme</label>
                    <select
                      className="input"
                      value={config.customHttp.authScheme}
                      onChange={(event) =>
                        updateConfig((prev) => ({
                          ...prev,
                          customHttp: {
                            ...prev.customHttp,
                            authScheme: event.target.value as EmailServerConfig["customHttp"]["authScheme"],
                          },
                        }))
                      }
                    >
                      <option value="none">None</option>
                      <option value="bearer">Bearer token</option>
                      <option value="basic">Basic auth</option>
                      <option value="header">Custom header</option>
                    </select>
                  </div>
                  {config.customHttp.authScheme === "bearer" && (
                    <div>
                      <label className="admin-email-settings__field-label">Bearer token</label>
                      <input
                        className="input"
                        type="password"
                        value={config.customHttp.authToken}
                        onChange={(event) =>
                          updateConfig((prev) => ({
                            ...prev,
                            customHttp: { ...prev.customHttp, authToken: event.target.value },
                          }))
                        }
                      />
                    </div>
                  )}
                  {config.customHttp.authScheme === "basic" && (
                    <>
                      <div>
                        <label className="admin-email-settings__field-label">Username</label>
                        <input
                          className="input"
                          value={config.customHttp.username}
                          onChange={(event) =>
                            updateConfig((prev) => ({
                              ...prev,
                              customHttp: {
                                ...prev.customHttp,
                                username: event.target.value,
                              },
                            }))
                          }
                        />
                      </div>
                      <div>
                        <label className="admin-email-settings__field-label">Password</label>
                        <input
                          className="input"
                          type="password"
                          value={config.customHttp.password}
                          onChange={(event) =>
                            updateConfig((prev) => ({
                              ...prev,
                              customHttp: {
                                ...prev.customHttp,
                                password: event.target.value,
                              },
                            }))
                          }
                        />
                      </div>
                    </>
                  )}
                  {config.customHttp.authScheme === "header" && (
                    <>
                      <div>
                        <label className="admin-email-settings__field-label">Header name</label>
                        <input
                          className="input"
                          value={config.customHttp.headerName}
                          onChange={(event) =>
                            updateConfig((prev) => ({
                              ...prev,
                              customHttp: {
                                ...prev.customHttp,
                                headerName: event.target.value,
                              },
                            }))
                          }
                        />
                      </div>
                      <div>
                        <label className="admin-email-settings__field-label">Header value</label>
                        <input
                          className="input"
                          type="password"
                          value={config.customHttp.headerValue}
                          onChange={(event) =>
                            updateConfig((prev) => ({
                              ...prev,
                              customHttp: {
                                ...prev.customHttp,
                                headerValue: event.target.value,
                              },
                            }))
                          }
                        />
                      </div>
                    </>
                  )}
                  <div>
                    <label className="admin-email-settings__field-label">Timeout (ms)</label>
                    <input
                      className="input"
                      type="number"
                      value={config.customHttp.timeoutMs}
                      onChange={(event) =>
                        updateConfig((prev) => ({
                          ...prev,
                          customHttp: {
                            ...prev.customHttp,
                            timeoutMs: Number(event.target.value),
                          },
                        }))
                      }
                    />
                  </div>
                </div>
              </Panel>
            )}

            <Panel
              title="Provider compatibility"
              className="admin-email-settings__panel"
              actions={
                <button
                  type="button"
                  className="admin-email-settings__help-btn"
                  onClick={() => openHelp("compatibility")}
                  aria-label="Provider compatibility notes"
                  title="Provider compatibility notes"
                >
                  ?
                </button>
              }
            >
              <p className="admin-email-settings__hint">
                Quick compatibility matrix is available in the notes panel.
              </p>
            </Panel>
          </div>

          <div className="admin-page__side">
            <Panel
              title="Realtime test console"
              className="admin-email-settings__panel"
              actions={
                <button
                  type="button"
                  className="admin-email-settings__help-btn"
                  onClick={() => openHelp("test-console")}
                  aria-label="Realtime test console notes"
                  title="Realtime test console notes"
                >
                  !
                </button>
              }
            >
              <div className="admin-email-settings__grid">
                <div>
                  <label className="admin-email-settings__field-label">Test endpoint URL</label>
                  <input
                    className="input"
                    placeholder="https://email.your-domain.com/test"
                    value={config.testEndpointUrl}
                    onChange={(event) =>
                      updateConfig((prev) => ({
                        ...prev,
                        testEndpointUrl: event.target.value,
                      }))
                    }
                  />
                </div>
                <div>
                  <label className="admin-email-settings__field-label">Timeout (ms)</label>
                  <input
                    className="input"
                    type="number"
                    value={config.testTimeoutMs}
                    onChange={(event) =>
                      updateConfig((prev) => ({
                        ...prev,
                        testTimeoutMs: Number(event.target.value),
                      }))
                    }
                  />
                </div>
              </div>
              <div className="admin-email-settings__toggle-row">
                <label className="admin-email-settings__toggle">
                  <input
                    type="checkbox"
                    checked={includeSecrets}
                    onChange={(event) => setIncludeSecrets(event.target.checked)}
                  />
                  Include secrets in test payload
                </label>
              </div>
              <div className="admin-email-settings__test-actions">
                <Button type="button" onClick={runConnectionTest} disabled={testState === "running"}>
                  {testState === "running" ? "Testing..." : "Run test"}
                </Button>
                {testLatencyMs !== null && (
                  <span className="admin-email-settings__latency">
                    {testLatencyMs} ms
                  </span>
                )}
              </div>
              <div className="admin-email-settings__metrics">
                <div className="admin-email-settings__metric">
                  <span className="admin-email-settings__metric-label">Latency</span>
                  <div className="admin-email-settings__metric-value">
                    {testLatencyMs !== null ? `${testLatencyMs} ms` : "—"}
                  </div>
                </div>
                <div className="admin-email-settings__metric">
                  <span className="admin-email-settings__metric-label">Payload size</span>
                  <div className="admin-email-settings__metric-value">
                    {testPayloadBytes !== null
                      ? `${(testPayloadBytes / 1024).toFixed(2)} KB`
                      : "—"}
                  </div>
                </div>
                <div className="admin-email-settings__metric">
                  <span className="admin-email-settings__metric-label">Estimated speed</span>
                  <div className="admin-email-settings__metric-value">
                    {renderSpeed(testPayloadBytes, testLatencyMs)}
                  </div>
                </div>
                <div className="admin-email-settings__metric">
                  <span className="admin-email-settings__metric-label">Last tested</span>
                  <div className="admin-email-settings__metric-value">
                    {renderTime(lastTestedAt)}
                  </div>
                </div>
                <div className="admin-email-settings__metric">
                  <span className="admin-email-settings__metric-label">Next test</span>
                  <div className="admin-email-settings__metric-value">
                    {renderTime(nextTestAt)}
                  </div>
                </div>
              </div>
              {testMessage && (
                <InlineAlert
                  tone={testState === "success" ? "success" : "danger"}
                  title={testState === "success" ? "Connected" : "Test failed"}
                >
                  <span>{testMessage}</span>
                </InlineAlert>
              )}
              {!testMessage && testState === "idle" && (
                <InlineAlert tone="info" title="How this works">
                  <span>
                    This console posts your settings to a HTTPS endpoint so you can
                    validate connectivity without backend changes.
                  </span>
                </InlineAlert>
              )}
            </Panel>
          </div>
        </div>
        {helpOpen && (
          <button
            type="button"
            className="admin-email-settings__backdrop"
            onClick={() => setHelpOpen(false)}
            aria-label="Close notes panel"
          />
        )}
        <aside
          className={
            "admin-email-settings__drawer" +
            (helpOpen ? " admin-email-settings__drawer--open" : "")
          }
        >
          <div className="admin-email-settings__drawer-header">
            <h3 className="admin-email-settings__drawer-title">{activeHelp.title}</h3>
            <button
              type="button"
              className="admin-email-settings__drawer-close"
              onClick={() => setHelpOpen(false)}
              aria-label="Close notes panel"
              title="Close"
            >
              ×
            </button>
          </div>
          <div className="admin-email-settings__drawer-body">{activeHelp.body}</div>
          <div className="admin-email-settings__drawer-footer">
            <button
              type="button"
              className="admin-email-settings__drawer-toggle"
              onClick={() => setHelpOpen(false)}
            >
              Collapse panel
            </button>
          </div>
        </aside>
      </div>
    </DepartmentLayout>
  );
};

export default EmailServerSettingsPage;
