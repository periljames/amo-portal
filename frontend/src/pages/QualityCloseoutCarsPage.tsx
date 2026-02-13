import React from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import QMSLayout from "../components/QMS/QMSLayout";
import { getContext } from "../services/auth";
import { qmsListCars, qmsListCarAttachments } from "../services/qms";

const QualityCloseoutCarsPage: React.FC = () => {
  const params = useParams<{ amoCode?: string }>();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const cars = useQuery({ queryKey: ["qms-cars", "closeout"], queryFn: () => qmsListCars({ status_: "PENDING_VERIFICATION" }) });
  const firstCar = cars.data?.[0];
  const attachments = useQuery({ queryKey: ["car-attachments", firstCar?.id], queryFn: () => qmsListCarAttachments(firstCar!.id), enabled: !!firstCar?.id });

  return (
    <QMSLayout amoCode={amoCode} department="quality" title="Closeout Workbench · CARs" subtitle="Review corrective action closure with inline attachments.">
      <div className="qms-card">
        {(cars.data ?? []).map((car) => (
          <div key={car.id} className="qms-dashboard-card" style={{ marginBottom: 8 }}>
            <strong>{car.car_number} · {car.title}</strong>
            <p>{car.summary}</p>
            <small>Attachments in current queue item: {attachments.data?.length ?? 0}</small>
          </div>
        ))}
      </div>
    </QMSLayout>
  );
};

export default QualityCloseoutCarsPage;
