import React from "react";
import { useQuery } from "@tanstack/react-query";
import QualityAuditsSectionLayout from "./qualityAudits/QualityAuditsSectionLayout";
import { qmsListCars, qmsListCarAttachments } from "../services/qms";

const QualityCloseoutCarsPage: React.FC = () => {
  const cars = useQuery({ queryKey: ["qms-cars", "closeout"], queryFn: () => qmsListCars({ status_: "PENDING_VERIFICATION" }) });
  const firstCar = cars.data?.[0];
  const attachments = useQuery({ queryKey: ["car-attachments", firstCar?.id], queryFn: () => qmsListCarAttachments(firstCar!.id), enabled: !!firstCar?.id });

  return (
    <QualityAuditsSectionLayout title="Closeout Workbench · CARs" subtitle="Review corrective action closure with inline attachments.">
      <div className="qms-card">
        {(cars.data ?? []).map((car) => (
          <div key={car.id} className="qms-dashboard-card" style={{ marginBottom: 8 }}>
            <strong>{car.car_number} · {car.title}</strong>
            <p>{car.summary}</p>
            <small>Attachments in current queue item: {attachments.data?.length ?? 0}</small>
          </div>
        ))}
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityCloseoutCarsPage;
