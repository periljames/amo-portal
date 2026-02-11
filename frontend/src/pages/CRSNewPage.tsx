import React, { useEffect } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { fetchSerialNumber, listAircraftOptions, submitCrsForm } from "../services/qmsCockpit";
import type { CRSCreate } from "../types/crs";

const crsSchema = z.object({
  serial: z.string().min(1),
  tailNumber: z.string().min(1, "Tail number is required"),
  engineHours: z.coerce.number().nonnegative(),
  engineCycles: z.coerce.number().nonnegative(),
  maintenanceSummary: z.string().min(1, "Maintenance summary is required"),
  issuedBy: z.string().min(1, "Issuer is required"),
  issueDate: z.string().min(1, "Issue date is required"),
});

type CrsFormValues = z.infer<typeof crsSchema>;

const CRSNewPage: React.FC = () => {
  const { amoCode } = useParams<{ amoCode?: string }>();
  const amoSlug = amoCode ?? "UNKNOWN";

  const { data: aircraft = [] } = useQuery({ queryKey: ["crs-aircraft-options"], queryFn: listAircraftOptions });
  const { data: serial } = useQuery({ queryKey: ["crs-serial"], queryFn: fetchSerialNumber });

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<CrsFormValues>({
    resolver: zodResolver(crsSchema),
    defaultValues: {
      serial: "",
      tailNumber: "",
      engineHours: 0,
      engineCycles: 0,
      maintenanceSummary: "",
      issuedBy: "",
      issueDate: new Date().toISOString().slice(0, 10),
    },
  });

  useEffect(() => {
    if (serial) setValue("serial", serial);
  }, [serial, setValue]);

  const tailNumber = watch("tailNumber");

  useEffect(() => {
    if (!tailNumber) return;
    const row = aircraft.find((item) => item.tailNumber === tailNumber);
    if (!row) return;
    setValue("engineHours", row.engineHours);
    setValue("engineCycles", row.engineCycles);
  }, [aircraft, tailNumber, setValue]);

  const createMutation = useMutation({ mutationFn: (payload: Record<string, unknown>) => submitCrsForm(payload) });

  const onSubmit = handleSubmit(async (values) => {
    const payload: CRSCreate = {
      aircraft_serial_number: values.tailNumber,
      wo_no: `WO-${Date.now()}`,
      releasing_authority: "KCAA",
      operator_contractor: "AMO Operator",
      location: "Main Base",
      aircraft_type: "Dash-8",
      aircraft_reg: values.tailNumber,
      aircraft_tat: values.engineHours,
      aircraft_tac: values.engineCycles,
      maintenance_carried_out: values.maintenanceSummary,
      date_of_completion: values.issueDate,
      amp_used: true,
      amm_used: true,
      mtx_data_used: false,
      airframe_limit_unit: "HOURS",
      issuer_full_name: values.issuedBy,
      issuer_auth_ref: "AUTH-001",
      issuer_license: "KCAA-LIC",
      crs_issue_date: values.issueDate,
      signoffs: [],
    };

    await createMutation.mutateAsync({ ...payload, crs_serial: values.serial });
    window.print();
  });

  return (
    <DepartmentLayout amoCode={amoSlug} activeDepartment="planning">
      <section className="paper-shell">
        <div className="paper-card">
          <header className="paper-header">
            <h1>Certificate of Release to Service (CRS)</h1>
            <button type="button" className="primary-chip-btn" onClick={() => window.print()}>
              Print / Export
            </button>
          </header>

          <form className="paper-form" onSubmit={onSubmit}>
            <label>
              CRS Serial Number
              <input readOnly {...register("serial")} />
              {errors.serial && <span>{errors.serial.message}</span>}
            </label>

            <label>
              Tail Number
              <select {...register("tailNumber")}>
                <option value="">Select tail number</option>
                {aircraft.map((item) => (
                  <option key={item.tailNumber} value={item.tailNumber}>
                    {item.tailNumber}
                  </option>
                ))}
              </select>
              {errors.tailNumber && <span>{errors.tailNumber.message}</span>}
            </label>

            <label>
              Engine Hours
              <input type="number" {...register("engineHours")} />
              {errors.engineHours && <span>{errors.engineHours.message}</span>}
            </label>

            <label>
              Engine Cycles
              <input type="number" {...register("engineCycles")} />
              {errors.engineCycles && <span>{errors.engineCycles.message}</span>}
            </label>

            <label>
              Maintenance Summary
              <textarea rows={4} {...register("maintenanceSummary")} />
              {errors.maintenanceSummary && <span>{errors.maintenanceSummary.message}</span>}
            </label>

            <label>
              Issued By
              <input {...register("issuedBy")} />
              {errors.issuedBy && <span>{errors.issuedBy.message}</span>}
            </label>

            <label>
              Issue Date
              <input type="date" {...register("issueDate")} />
              {errors.issueDate && <span>{errors.issueDate.message}</span>}
            </label>

            <div className="paper-actions">
              <button type="submit" className="primary-chip-btn" disabled={createMutation.isPending}>
                {createMutation.isPending ? "Saving..." : "Save CRS"}
              </button>
            </div>
          </form>
        </div>
      </section>
    </DepartmentLayout>
  );
};

export default CRSNewPage;
