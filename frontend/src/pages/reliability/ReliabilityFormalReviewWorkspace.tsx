import React, { useEffect, useMemo, useState } from "react";

import {
  createFormalReport,
  freezeFormalReport,
  getFormalReport,
  listFormalProfiles,
  listFormalReports,
  openFormalReportArtifact,
  renderFormalReport,
  runFormalCompleteness,
  transitionFormalReport,
  updateFormalRequirement,
  updateFormalSection,
  type FormalArtifactKind,
  type FormalCompleteness,
  type FormalPeriodType,
  type FormalProfile,
  type FormalReport,
  type FormalReportStatus,
  type FormalRequirementAssessment,
  type FormalSection,
  type RequirementAssessmentStatus,
} from "./reliabilityFormalReportingApi";
import "./ReliabilityFormalReviewWorkspace.css";

const PERIOD_OPTIONS: Array<{ value: FormalPeriodType; label: string }> = [
  { value: "MONTHLY", label: "Monthly" },
  { value: "QUARTERLY", label: "Quarterly" },
  { value: "HALF_YEAR", label: "Six-month / half-year" },
  { value: "ANNUAL", label: "Annual" },
  { value: "YEAR_TO_DATE", label: "Year to date" },
  { value: "ROLLING_3_MONTH", label: "Rolling 3 months" },
  { value: "ROLLING_6_MONTH", label: "Rolling 6 months" },
  { value: "ROLLING_12_MONTH", label: "Rolling 12 months" },
  { value: "CUSTOM", label: "Controlled custom dates" },
];

const NEXT_STATUS: Partial<Record<FormalReportStatus, FormalReportStatus>> = {
  DATA_REVIEW: "TECHNICAL_REVIEW",
  TECHNICAL_REVIEW: "QUALITY_REVIEW",
  QUALITY_REVIEW: "APPROVAL_PENDING",
  APPROVAL_PENDING: "APPROVED",
  APPROVED: "PUBLISHED",
};

const NEXT_LABEL: Partial<Record<FormalReportStatus, string>> = {
  DATA_REVIEW: "Submit technical review",
  TECHNICAL_REVIEW: "Submit quality review",
  QUALITY_REVIEW: "Submit for approval",
  APPROVAL_PENDING: "Approve revision",
  APPROVED: "Publish controlled revision",
};

const COMMENTARY_KINDS = [
  "OBSERVED_FACT",
  "STATISTICAL_INTERPRETATION",
  "ENGINEERING_JUDGEMENT",
  "RECOMMENDATION",
  "MANAGEMENT_DECISION",
] as const;

function defaultWindow(): { start: string; end: string } {
  const now = new Date();
  const year = now.getFullYear();
  if (now.getMonth() < 6) {
    return { start: `${year}-01-01`, end: `${year}-06-30` };
  }
  return { start: `${year}-07-01`, end: `${year}-12-31` };
}

function statusTone(status: string): string {
  if (["PUBLISHED", "APPROVED", "READY", "SATISFIED"].includes(status)) return "good";
  if (["GAP", "WITHDRAWN"].includes(status)) return "bad";
  if (["WITHHELD", "SUPERSEDED", "NOT_APPLICABLE"].includes(status)) return "muted";
  return "active";
}

function shortHash(value?: string | null): string {
  if (!value) return "Not retained";
  return `${value.slice(0, 12)}…${value.slice(-8)}`;
}

function reportLabel(report: FormalReport): string {
  return `${report.report_number} · Rev ${report.revision}`;
}

function requirementTitle(row: FormalRequirementAssessment): string {
  return row.requirement.requirement_key || row.requirement.source_reference || row.requirement_id;
}

const ReliabilityFormalReviewWorkspace: React.FC = () => {
  const initialWindow = useMemo(defaultWindow, []);
  const [profiles, setProfiles] = useState<FormalProfile[]>([]);
  const [reports, setReports] = useState<FormalReport[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [report, setReport] = useState<FormalReport | null>(null);
  const [selectedSectionCode, setSelectedSectionCode] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>("");
  const [message, setMessage] = useState<string>("");
  const [completeness, setCompleteness] = useState<FormalCompleteness | null>(null);

  const [profileId, setProfileId] = useState("");
  const [periodType, setPeriodType] = useState<FormalPeriodType>("HALF_YEAR");
  const [periodStart, setPeriodStart] = useState(initialWindow.start);
  const [periodEnd, setPeriodEnd] = useState(initialWindow.end);
  const [reportNumber, setReportNumber] = useState("");
  const [reportTitle, setReportTitle] = useState("Reliability Programme Review");
  const [aircraftInput, setAircraftInput] = useState("");

  const [sectionStatus, setSectionStatus] = useState<FormalSection["status"]>("DRAFT");
  const [commentaryKind, setCommentaryKind] = useState<(typeof COMMENTARY_KINDS)[number]>("ENGINEERING_JUDGEMENT");
  const [commentaryText, setCommentaryText] = useState("");

  const [requirementStatus, setRequirementStatus] = useState<RequirementAssessmentStatus>("GAP");
  const [requirementNote, setRequirementNote] = useState("");
  const [requirementEvidence, setRequirementEvidence] = useState("");
  const [activeRequirementId, setActiveRequirementId] = useState("");

  function adoptReport(detail: FormalReport) {
    setReport(detail);
    setCompleteness(detail.completeness || null);
    const current = detail.sections?.find((item) => item.code === selectedSectionCode);
    const next = current || detail.sections?.[0] || null;
    setSelectedSectionCode(next?.code || "");
    setSectionStatus(next?.status || "DRAFT");
    setCommentaryText("");
  }

  async function refreshReports(preferredId?: string) {
    const payload = await listFormalReports();
    setReports(payload.reports);
    const nextId = preferredId || selectedId || payload.reports[0]?.id || "";
    if (nextId) setSelectedId(nextId);
  }

  async function loadReport(id: string) {
    if (!id) {
      setReport(null);
      return;
    }
    const detail = await getFormalReport(id);
    adoptReport(detail);
  }

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        setLoading(true);
        const [profileRows, reportRows] = await Promise.all([listFormalProfiles(), listFormalReports()]);
        if (!active) return;
        setProfiles(profileRows);
        setReports(reportRows.reports);
        setProfileId(profileRows[0]?.id || "");
        setSelectedId(reportRows.reports[0]?.id || "");
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Unable to load formal Reliability reporting.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    if (!selectedId) {
      return () => {
        active = false;
      };
    }
    void (async () => {
      try {
        const detail = await getFormalReport(selectedId);
        if (!active) return;
        setReport(detail);
        setCompleteness(detail.completeness || null);
        const first = detail.sections?.[0] || null;
        setSelectedSectionCode((current) =>
          detail.sections?.some((item) => item.code === current) ? current : first?.code || ""
        );
        setSectionStatus(first?.status || "DRAFT");
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Unable to open formal Reliability report.");
      }
    })();
    return () => {
      active = false;
    };
  }, [selectedId]);

  const selectedSection = report?.sections?.find((item) => item.code === selectedSectionCode) || null;
  const sectionRequirements = (report?.requirements || []).filter(
    (item) => !selectedSectionCode || item.section_code === selectedSectionCode
  );
  const blockingFailures = completeness?.checks?.filter((item) => item.blocking && !item.passed) || [];

  function selectSection(section: FormalSection) {
    setSelectedSectionCode(section.code);
    setSectionStatus(section.status);
    setCommentaryText("");
    setActiveRequirementId("");
  }

  async function perform(label: string, action: () => Promise<FormalReport | void>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await action();
      if (result) {
        adoptReport(result);
        setSelectedId(result.id);
        await refreshReports(result.id);
      }
      setMessage(label);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The controlled action could not be completed.");
    } finally {
      setBusy(false);
    }
  }

  async function onCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!profileId || !reportNumber.trim()) {
      setError("Select a regulatory profile and enter a controlled report number.");
      return;
    }
    await perform("Draft formal report created.", async () => {
      const created = await createFormalReport({
        profile_id: profileId,
        report_number: reportNumber.trim(),
        title: reportTitle.trim() || "Reliability Programme Review",
        period_type: periodType,
        period_start: periodStart,
        period_end: periodEnd,
      });
      setReportNumber("");
      return created;
    });
  }

  async function onFreeze() {
    if (!report) return;
    const aircraft = aircraftInput
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    await perform("Data cutoff and fleet effectivity frozen.", () =>
      freezeFormalReport(report.id, {
        aircraft_serial_numbers: aircraft,
        effectivity: { selection_source: "FORMAL_REVIEW_WORKSPACE" },
      })
    );
  }

  async function onSaveSection() {
    if (!report || !selectedSection) return;
    const existing = selectedSection.commentary || [];
    const nextCommentary = commentaryText.trim()
      ? [...existing, { kind: commentaryKind, text: commentaryText.trim(), evidence_refs: selectedSection.evidence_refs || [] }]
      : existing;
    await perform("Controlled section updated.", () =>
      updateFormalSection(report.id, selectedSection.code, {
        status: sectionStatus,
        commentary: nextCommentary,
        evidence_refs: selectedSection.evidence_refs,
        warnings: selectedSection.warnings,
      })
    );
    setCommentaryText("");
  }

  async function onCompleteness() {
    if (!report) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await runFormalCompleteness(report.id);
      setCompleteness(result);
      setMessage(result.passed ? "Completeness gate passed." : "Completeness gate identified blocking items.");
      await loadReport(report.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Completeness assessment failed.");
    } finally {
      setBusy(false);
    }
  }

  function beginRequirementEdit(row: FormalRequirementAssessment) {
    setActiveRequirementId(row.id);
    setRequirementStatus(row.status);
    setRequirementNote(row.reviewer_note || "");
    setRequirementEvidence("");
  }

  async function onSaveRequirement(row: FormalRequirementAssessment) {
    if (!report) return;
    const note = requirementNote.trim();
    const evidence = requirementEvidence.trim();
    if (requirementStatus === "SATISFIED" && (!note || !evidence)) {
      setError("A SATISFIED requirement needs a reviewer note and a retained evidence reference.");
      return;
    }
    if (requirementStatus === "NOT_APPLICABLE" && !note) {
      setError("A NOT_APPLICABLE decision needs a rationale.");
      return;
    }
    await perform("Regulatory requirement assessment updated.", () =>
      updateFormalRequirement(report.id, row.id, {
        applicable: requirementStatus !== "NOT_APPLICABLE",
        status: requirementStatus,
        reviewer_note: note || null,
        source_refs: evidence ? [{ kind: "CONTROLLED_REFERENCE", reference: evidence }] : row.source_refs,
        evidence_refs: row.evidence_refs,
        calculation_refs: row.calculation_refs,
      })
    );
    setActiveRequirementId("");
  }

  async function onTransition() {
    if (!report) return;
    const next = NEXT_STATUS[report.status];
    if (!next) return;
    await perform(`${NEXT_LABEL[report.status] || "Lifecycle transition"} completed.`, () =>
      transitionFormalReport(report.id, next, `Advanced from Reliability Review workspace to ${next}.`)
    );
  }

  async function onOpenArtifact(kind: FormalArtifactKind) {
    if (!report) return;
    await perform(
      kind === "pdf" ? "Retained PDF opened with authenticated access." : "Retained report opened with authenticated access.",
      async () => {
        await openFormalReportArtifact(report.id, kind);
      }
    );
  }

  if (loading) {
    return <div className="rfw-loading" role="status">Loading controlled Reliability reporting…</div>;
  }

  return (
    <main className="rfw-shell">
      <header className="rfw-header">
        <div>
          <p className="rfw-eyebrow">Reliability Programme</p>
          <h1>Formal review workspace</h1>
          <p>Prepare, evidence, review and publish retained Reliability Programme reports without rebuilding the analysis in spreadsheets.</p>
        </div>
        <div className="rfw-header-state" aria-label="Current report state">
          <span className={`rfw-chip ${statusTone(report?.status || "DRAFT")}`}>{report?.status || "No report selected"}</span>
          {report && <strong>{reportLabel(report)}</strong>}
        </div>
      </header>

      {(error || message) && (
        <div className={`rfw-banner ${error ? "error" : "success"}`} role={error ? "alert" : "status"}>
          {error || message}
        </div>
      )}

      <section className="rfw-create" aria-labelledby="rfw-create-title">
        <div className="rfw-create-copy">
          <p className="rfw-eyebrow">New controlled period</p>
          <h2 id="rfw-create-title">Start formal report</h2>
          <p>The selected profile determines required chapters, evidence rules and publication gates.</p>
        </div>
        <form onSubmit={onCreate} className="rfw-create-form">
          <label>
            Regulatory profile
            <select value={profileId} onChange={(event) => setProfileId(event.target.value)} disabled={busy}>
              {profiles.map((profile) => (
                <option key={profile.id} value={profile.id}>{profile.code} · {profile.version}</option>
              ))}
            </select>
          </label>
          <label>
            Period
            <select value={periodType} onChange={(event) => setPeriodType(event.target.value as FormalPeriodType)} disabled={busy}>
              {PERIOD_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <label>
            Start
            <input type="date" value={periodStart} onChange={(event) => setPeriodStart(event.target.value)} required disabled={busy} />
          </label>
          <label>
            End
            <input type="date" value={periodEnd} onChange={(event) => setPeriodEnd(event.target.value)} required disabled={busy} />
          </label>
          <label>
            Report number
            <input value={reportNumber} onChange={(event) => setReportNumber(event.target.value)} placeholder="REL-2026-H2" required disabled={busy} />
          </label>
          <label>
            Report title
            <input value={reportTitle} onChange={(event) => setReportTitle(event.target.value)} required disabled={busy} />
          </label>
          <button type="submit" className="rfw-primary" disabled={busy || !profileId}>Create draft</button>
        </form>
      </section>

      <div className="rfw-grid">
        <aside className="rfw-library" aria-label="Formal report library">
          <div className="rfw-panel-title">
            <div><p className="rfw-eyebrow">Library</p><h2>Report revisions</h2></div>
            <span>{reports.length}</span>
          </div>
          <div className="rfw-report-list">
            {reports.length === 0 && <p className="rfw-empty">No formal report revision has been created.</p>}
            {reports.map((item) => (
              <button
                key={item.id}
                type="button"
                className={item.id === selectedId ? "selected" : ""}
                onClick={() => setSelectedId(item.id)}
              >
                <strong>{item.report_number}</strong>
                <span>{item.period_start} — {item.period_end}</span>
                <small>Rev {item.revision} · {item.profile_code}</small>
                <em className={statusTone(item.status)}>{item.status}</em>
              </button>
            ))}
          </div>
        </aside>

        <section className="rfw-workspace" aria-label="Formal Reliability report preparation">
          {!report ? (
            <div className="rfw-empty large">Create or select a formal report revision to begin the controlled review.</div>
          ) : (
            <>
              <div className="rfw-control-strip">
                <div><span>Period</span><strong>{report.period_start} — {report.period_end}</strong></div>
                <div><span>Profile</span><strong>{report.profile_code} · {report.profile_version}</strong></div>
                <div><span>Data cutoff</span><strong>{report.data_cutoff_at ? new Date(report.data_cutoff_at).toLocaleString() : "Not frozen"}</strong></div>
                <div><span>HTML</span><strong title={report.html_sha256 || ""}>{shortHash(report.html_sha256)}</strong></div>
                <div><span>PDF</span><strong title={report.pdf_sha256 || ""}>{shortHash(report.pdf_sha256)}</strong></div>
              </div>

              <div className="rfw-actionbar">
                {!report.effectivity_frozen_at && (
                  <label className="rfw-effectivity-input">
                    Aircraft effectivity
                    <input
                      value={aircraftInput}
                      onChange={(event) => setAircraftInput(event.target.value)}
                      placeholder="Blank = tenant fleet; or 5Y-ABC, 5Y-DEF"
                      disabled={busy}
                    />
                  </label>
                )}
                {!report.effectivity_frozen_at && <button type="button" onClick={onFreeze} disabled={busy}>Freeze cutoff & effectivity</button>}
                {report.effectivity_frozen_at && !["APPROVED", "PUBLISHED", "SUPERSEDED", "WITHDRAWN"].includes(report.status) && (
                  <button type="button" onClick={() => void perform("Formal HTML/PDF regenerated from the frozen snapshot.", () => renderFormalReport(report.id))} disabled={busy}>Generate retained report</button>
                )}
                <button type="button" onClick={onCompleteness} disabled={busy}>Run completeness</button>
                {report.html_sha256 && <button type="button" onClick={() => void onOpenArtifact("view")} disabled={busy}>Open retained view</button>}
                {report.pdf_sha256 && <button type="button" onClick={() => void onOpenArtifact("pdf")} disabled={busy}>Open PDF</button>}
                {NEXT_STATUS[report.status] && (
                  <button type="button" className="rfw-primary" onClick={onTransition} disabled={busy}>{NEXT_LABEL[report.status]}</button>
                )}
              </div>

              <div className="rfw-review-grid">
                <nav className="rfw-chapters" aria-label="Formal report chapters">
                  <h3>Chapters</h3>
                  {(report.sections || []).map((section) => (
                    <button
                      key={section.id}
                      type="button"
                      className={section.code === selectedSectionCode ? "selected" : ""}
                      onClick={() => selectSection(section)}
                    >
                      <span>{String(section.sequence).padStart(2, "0")}</span>
                      <strong>{section.title}</strong>
                      <em className={statusTone(section.status)}>{section.status}</em>
                    </button>
                  ))}
                </nav>

                <article className="rfw-canvas">
                  {selectedSection && (
                    <>
                      <div className="rfw-section-heading">
                        <div>
                          <p className="rfw-eyebrow">Chapter {selectedSection.sequence}</p>
                          <h2>{selectedSection.title}</h2>
                        </div>
                        <span className={`rfw-chip ${statusTone(selectedSection.status)}`}>{selectedSection.status}</span>
                      </div>

                      <div className="rfw-data-block">
                        <h3>Governed analytical payload</h3>
                        {Object.keys(selectedSection.computed_data || {}).length > 0 ? (
                          <pre>{JSON.stringify(selectedSection.computed_data, null, 2)}</pre>
                        ) : (
                          <p className="rfw-empty">This chapter does not yet have a mapped computed payload. Commentary can still be controlled, but unsupported narrative must not be introduced.</p>
                        )}
                      </div>

                      <div className="rfw-commentary">
                        <div className="rfw-panel-title"><div><h3>Engineering interpretation</h3><p>Separate facts, statistical interpretation, engineering judgement and decisions.</p></div></div>
                        {(selectedSection.commentary || []).map((item, index) => (
                          <div className="rfw-comment" key={`${selectedSection.id}-${index}`}>
                            <strong>{String(item.kind || "ENGINEERING_JUDGEMENT")}</strong>
                            <p>{String(item.text || item.comment || "")}</p>
                          </div>
                        ))}
                        <div className="rfw-editor-row">
                          <select value={commentaryKind} onChange={(event) => setCommentaryKind(event.target.value as (typeof COMMENTARY_KINDS)[number])} disabled={busy}>
                            {COMMENTARY_KINDS.map((kind) => <option key={kind} value={kind}>{kind.replaceAll("_", " ")}</option>)}
                          </select>
                          <select value={sectionStatus} onChange={(event) => setSectionStatus(event.target.value as FormalSection["status"])} disabled={busy}>
                            <option value="DRAFT">Draft</option>
                            <option value="READY">Ready</option>
                            <option value="WITHHELD">Withheld</option>
                            <option value="NOT_APPLICABLE">Not applicable</option>
                          </select>
                        </div>
                        <textarea
                          value={commentaryText}
                          onChange={(event) => setCommentaryText(event.target.value)}
                          placeholder="Add traceable engineering interpretation. Do not fill missing evidence with assumptions."
                          rows={5}
                          disabled={busy}
                        />
                        <button type="button" onClick={onSaveSection} disabled={busy}>Save controlled section</button>
                      </div>
                    </>
                  )}
                </article>

                <aside className="rfw-review-rail" aria-label="Regulatory completeness and evidence">
                  <div className="rfw-completeness-head">
                    <div><p className="rfw-eyebrow">Completeness</p><h3>{completeness?.passed ? "Ready for governed gate" : "Review required"}</h3></div>
                    <span className={`rfw-score ${completeness?.passed ? "good" : "bad"}`}>{blockingFailures.length}</span>
                  </div>
                  {blockingFailures.length > 0 && (
                    <div className="rfw-blockers">
                      {blockingFailures.slice(0, 6).map((item) => <p key={item.code}>{item.message}</p>)}
                    </div>
                  )}

                  <h3>Applicable requirements</h3>
                  <div className="rfw-requirements">
                    {sectionRequirements.length === 0 && <p className="rfw-empty">No requirement is mapped to this chapter.</p>}
                    {sectionRequirements.map((row) => (
                      <div key={row.id} className="rfw-requirement">
                        <div className="rfw-requirement-head">
                          <strong>{requirementTitle(row)}</strong>
                          <span className={`rfw-chip ${statusTone(row.status)}`}>{row.status}</span>
                        </div>
                        <p>{row.requirement.controlled_summary || "Controlled requirement summary unavailable."}</p>
                        <small>{row.requirement.source_reference}{row.requirement.paragraph_reference ? ` · ${row.requirement.paragraph_reference}` : ""}</small>
                        {activeRequirementId === row.id ? (
                          <div className="rfw-requirement-editor">
                            <select value={requirementStatus} onChange={(event) => setRequirementStatus(event.target.value as RequirementAssessmentStatus)} disabled={busy}>
                              <option value="SATISFIED">Satisfied</option>
                              <option value="NOT_APPLICABLE">Not applicable</option>
                              <option value="WITHHELD">Withheld</option>
                              <option value="GAP">Gap</option>
                              <option value="SUPERSEDED">Superseded</option>
                            </select>
                            <textarea value={requirementNote} onChange={(event) => setRequirementNote(event.target.value)} rows={3} placeholder="Reviewer note / applicability rationale" disabled={busy} />
                            <input value={requirementEvidence} onChange={(event) => setRequirementEvidence(event.target.value)} placeholder="Controlled source/calculation reference" disabled={busy} />
                            <div><button type="button" onClick={() => onSaveRequirement(row)} disabled={busy}>Save assessment</button><button type="button" onClick={() => setActiveRequirementId("")} disabled={busy}>Cancel</button></div>
                          </div>
                        ) : (
                          <button type="button" onClick={() => beginRequirementEdit(row)} disabled={busy || ["PUBLISHED", "SUPERSEDED", "WITHDRAWN"].includes(report.status)}>Review requirement</button>
                        )}
                      </div>
                    ))}
                  </div>
                </aside>
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
};

export default ReliabilityFormalReviewWorkspace;
