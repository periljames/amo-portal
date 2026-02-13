import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import QualityAuditsSectionLayout from "./qualityAudits/QualityAuditsSectionLayout";
import { getContext } from "../services/auth";
import { qmsListCars, qmsListCarAttachments } from "../services/qms";

const QualityEvidenceLibraryPage: React.FC = () => {
  const params = useParams<{ amoCode?: string }>();
  const ctx = getContext();
  const navigate = useNavigate();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const cars = useQuery({ queryKey: ["qms-cars", "evidence"], queryFn: () => qmsListCars({}) });
  const carId = cars.data?.[0]?.id;
  const attachments = useQuery({ queryKey: ["car-attachments", carId], queryFn: () => qmsListCarAttachments(carId || ""), enabled: !!carId });

  return (
    <QualityAuditsSectionLayout title="Evidence Library" subtitle="Global quality evidence with direct viewer handoff.">
      <div className="qms-card">
        {(attachments.data ?? []).map((file) => (
          <div key={file.id} className="qms-dashboard-card" style={{ marginBottom: 8 }}>
            <strong>{file.filename}</strong>
            <p>{file.content_type || "Unknown type"} · {file.size_bytes ?? 0} bytes</p>
            <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/quality/evidence/${file.id}`)}>Open viewer</button>
          </div>
        ))}
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityEvidenceLibraryPage;
