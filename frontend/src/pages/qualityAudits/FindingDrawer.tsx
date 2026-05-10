import React, { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Drawer from "../../components/shared/Drawer";
import {
  qmsCloseFinding,
  qmsListCarAttachments,
  qmsVerifyFinding,
  type CARAttachmentOut,
  type CAROut,
  type QMSFindingOut,
} from "../../services/qms";
import { getApiBaseUrl } from "../../services/config";

type Props = {
  isOpen: boolean;
  amoCode: string;
  department: string;
  finding: QMSFindingOut | null;
  linkedCar: CAROut | null;
  onClose: () => void;
};

type EvidenceItem = {
  id: string;
  filename: string;
  source: string;
  mime: string;
  url: string;
  uploadedAt?: string | null;
};

const monoStyle: React.CSSProperties = {
  fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace',
};

const severityPillClass = (value: string): string => {
  const upper = value.toUpperCase();
  if (upper === "CRITICAL" || upper === "LEVEL_1") return "qms-pill qms-pill--danger";
  if (upper === "MAJOR" || upper === "LEVEL_2") return "qms-pill qms-pill--warning";
  return "qms-pill";
};

const formatDateTime = (value?: string | null): string => {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
};

const toEvidenceFromAttachment = (item: CARAttachmentOut): EvidenceItem => {
  const lower = item.filename.toLowerCase();
  const fallback =
    lower.endsWith(".pdf")
      ? "application/pdf"
      : lower.endsWith(".png")
      ? "image/png"
      : lower.endsWith(".jpg") || lower.endsWith(".jpeg")
      ? "image/jpeg"
      : lower.endsWith(".docx")
      ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      : "application/octet-stream";

  return {
    id: item.id,
    filename: item.filename,
    source: "CAR attachment",
    mime: item.content_type || fallback,
    url: item.download_url,
    uploadedAt: item.uploaded_at,
  };
};

const FindingDrawer: React.FC<Props> = ({ isOpen, amoCode, department, finding, linkedCar, onClose }) => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const attachmentsQuery = useQuery({
    queryKey: ["qms-car-attachments", amoCode, linkedCar?.id],
    queryFn: () => qmsListCarAttachments(linkedCar?.id || ""),
    enabled: isOpen && !!linkedCar?.id,
    staleTime: 60_000,
  });

  const evidence = useMemo<EvidenceItem[]>(() => {
    const rows: EvidenceItem[] = [];
    (attachmentsQuery.data ?? []).forEach((item) => rows.push(toEvidenceFromAttachment(item)));

    if (linkedCar?.evidence_ref) {
      rows.push({
        id: `car-evidence-ref-${linkedCar.id}`,
        filename: "CAR evidence reference",
        source: "CAR evidence_ref",
        mime: "text/plain",
        url: linkedCar.evidence_ref,
      });
    }

    if (finding?.objective_evidence) {
      rows.push({
        id: `finding-evidence-${finding.id}`,
        filename: "Finding objective evidence",
        source: "Finding objective_evidence",
        mime: "text/plain",
        url: `${getApiBaseUrl()}/quality/findings/${finding.id}`,
      });
    }

    return rows;
  }, [attachmentsQuery.data, finding, linkedCar]);

  const verifyCloseMutation = useMutation({
    mutationFn: async () => {
      if (!finding) return null;
      await qmsVerifyFinding(finding.id, { objective_evidence: finding.objective_evidence ?? linkedCar?.evidence_ref ?? null });
      return qmsCloseFinding(finding.id);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["qms-findings"] });
      await queryClient.invalidateQueries({ queryKey: ["qms-cars"] });
      onClose();
    },
  });

  const openEvidence = (item: EvidenceItem) => {
    if (item.mime === "text/plain") return;
    navigate(
      `/maintenance/${amoCode}/qms/evidence-vault/${item.id}?name=${encodeURIComponent(item.filename)}&mime=${encodeURIComponent(item.mime)}&url=${encodeURIComponent(item.url)}&source=${encodeURIComponent(item.source)}`
    );
  };

  return (
    <Drawer title="Finding review" isOpen={isOpen} onClose={onClose}>
      {!finding ? (
        <div className="qms-card">Select a finding.</div>
      ) : (
        <div className="qms-finding-drawer">
          <section className="qms-card">
            <div className="qms-header__actions" style={{ justifyContent: "space-between" }}>
              <div>
                <div style={monoStyle}>{finding.finding_ref ?? finding.id}</div>
                <small style={monoStyle}>{finding.requirement_ref ?? "Requirement not specified"}</small>
              </div>
              <span className={severityPillClass(finding.severity)}>{finding.severity}</span>
            </div>
            <div style={{ marginTop: 8 }}>
              <strong>Accepted:</strong> <span style={monoStyle}>{formatDateTime(finding.acknowledged_at ?? finding.created_at)}</span>
            </div>
          </section>

          <section className="qms-card">
            <h4 style={{ marginTop: 0 }}>Statement of fact</h4>
            <p style={{ marginBottom: 0 }}>{finding.description || "No statement recorded."}</p>
          </section>

          <section className="qms-card">
            <h4 style={{ marginTop: 0 }}>Root cause analysis</h4>
            <p style={{ marginBottom: 0 }}>{linkedCar?.root_cause_text ?? linkedCar?.root_cause ?? "No RCA submitted yet."}</p>
          </section>

          <section className="qms-card">
            <h4 style={{ marginTop: 0 }}>Corrective Action Plan</h4>
            <div className="qms-grid" style={{ gridTemplateColumns: "1fr", gap: 10 }}>
              <div>
                <strong>Immediate action</strong>
                <p style={{ margin: "4px 0 0" }}>{linkedCar?.containment_action ?? "Not provided."}</p>
              </div>
              <div>
                <strong>Preventive action</strong>
                <p style={{ margin: "4px 0 0" }}>{linkedCar?.preventive_action ?? "Not provided."}</p>
              </div>
            </div>
          </section>

          <section className="qms-card">
            <h4 style={{ marginTop: 0 }}>Evidence vault</h4>
            {attachmentsQuery.isLoading ? <div className="qms-skeleton-block" /> : null}
            {evidence.length === 0 ? <p style={{ marginBottom: 0 }}>No linked evidence items.</p> : (
              <div className="qms-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10 }}>
                {evidence.map((item) => (
                  <button key={item.id} type="button" className="qms-card qms-card--interactive" onClick={() => openEvidence(item)} disabled={item.mime === "text/plain"}>
                    <strong>{item.filename}</strong>
                    <div style={{ marginTop: 6 }}>{item.source}</div>
                    <small>{item.uploadedAt ? formatDateTime(item.uploadedAt) : "Manual reference"}</small>
                  </button>
                ))}
              </div>
            )}
          </section>

          <div className="qms-header__actions" style={{ padding: 16 }}>
            <button type="button" className="btn btn-primary" onClick={() => verifyCloseMutation.mutate()} disabled={verifyCloseMutation.isPending || !finding}>
              {verifyCloseMutation.isPending ? "Verifying…" : "Verify & Close"}
            </button>
            {verifyCloseMutation.isError ? <span className="text-danger">{(verifyCloseMutation.error as Error).message || "Failed to verify and close."}</span> : null}
          </div>
        </div>
      )}
    </Drawer>
  );
};

export default FindingDrawer;
