// src/pages/CRSNewPage.tsx
import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import type {
  CRSCreate,
  ReleasingAuthority,
  AirframeLimitUnit,
  CRSPrefill,
} from "../types/crs";
import {
  createCRS,
  prefillCRS,
  fetchCRSTemplateMeta,
  fetchCRSTemplatePdf,
} from "../services/crs";
import type { CRSTemplateMeta } from "../services/crs";
import { Document, Page, pdfjs } from "react-pdf";

// ✅ FIX: Ensure worker version matches react-pdf's bundled pdfjs-dist
import pdfWorkerUrl from "react-pdf/node_modules/pdfjs-dist/build/pdf.worker.min.mjs?url";
pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

const defaultReleasing: ReleasingAuthority = "KCAA";
const defaultUnit: AirframeLimitUnit = "HOURS";

type CRSFieldElement =
  | HTMLInputElement
  | HTMLTextAreaElement
  | HTMLSelectElement;

type PdfFieldMeta = {
  pdf_name: string;
  model_key: string | null;
  page: number;
  left_pct: number;
  top_pct: number;
  width_pct: number;
  height_pct: number;
  field_type: "text" | "checkbox";
  multiline?: boolean;
};

// Map PDF field names to our local form state keys.
// This is the only CRS-specific mapping; the geometry comes from the backend.
const PDF_FIELD_TO_MODEL_KEY: Record<string, string> = {
  // Header / linkage
  "WO#": "wo_no",
  Operator_Contractor: "operator_contractor",
  Job_No: "job_no",
  Location: "location",

  // Aircraft identity
  Aircraft_Type: "aircraft_type",
  Aircraft_Registration: "aircraft_reg",
  Msn: "msn",

  // Engines
  LH_Engine_Type: "lh_engine_type",
  RH_Engine_Type: "rh_engine_type",
  LH_Engine_SNo: "lh_engine_sno",
  RH_Engine_SNo: "rh_engine_sno",

  // Utilisation snapshot
  Aircraft_TAT: "aircraft_tat",
  Aircraft_TAC: "aircraft_tac",
  LH_Hrs: "lh_hrs",
  LH_Cyc: "lh_cyc",
  RH_Hrs: "rh_hrs",
  RH_Cyc: "rh_cyc",

  // Work performed
  "Maintenance Carried out": "maintenance_carried_out",
  Deferred_Maintenance: "deferred_maintenance",
  Date_of_Completion: "date_of_completion",

  // Maintenance data flags
  AMP: "amp_used",
  AMM: "amm_used",
  "Mtx Data": "mtx_data_used",

  // Maintenance data references
  AMP_Reference: "amp_reference",
  AMP_Revision: "amp_revision",
  AMP_Issue_Date: "amp_issue_date",
  AMM_Reference: "amm_reference",
  AMM_Revision: "amm_revision",
  AMM_Issue_Date: "amm_issue_date",
  Add_Mtx_Data: "add_mtx_data",
  Work_Order_No: "work_order_no",

  // Expiry
  "Expiry Date": "expiry_date",
  "Hrs to Expiry": "hrs_to_expiry",
  "SUM (Aircraft TAT, Hrs to Expiry)": "sum_airframe_tat_expiry",
  "Next Maintenance Due": "next_maintenance_due",

  // CRS header
  "CRS Issue Date": "crs_issue_date",
};

function errMsg(err: unknown, fallback: string) {
  if (err instanceof Error) return err.message || fallback;
  if (typeof err === "string") return err || fallback;
  if (err && typeof err === "object" && "message" in err) {
    const m = (err as any).message;
    if (typeof m === "string" && m.trim()) return m.trim();
  }
  return fallback;
}

// ✅ Your current TS types are missing Page props like width/scale.
// Runtime supports them, so we wrap to unblock TS without breaking behavior.
const PdfDocument = Document as unknown as React.ComponentType<any>;
const PdfPage = Page as unknown as React.ComponentType<any>;

const CRSNewPage: React.FC = () => {
  const navigate = useNavigate();
  const { amoCode, department } = useParams<{
    amoCode: string;
    department: string;
  }>();

  const [form, setForm] = useState({
    // linkage
    aircraft_serial_number: "",
    releasing_authority: defaultReleasing as ReleasingAuthority,
    operator_contractor: "Safarilink Aviation Ltd",
    job_no: "",
    wo_no: "",
    location: "HKNA",

    // aircraft & engines
    aircraft_type: "",
    aircraft_reg: "",
    msn: "",
    lh_engine_type: "",
    rh_engine_type: "",
    lh_engine_sno: "",
    rh_engine_sno: "",
    aircraft_tat: "",
    aircraft_tac: "",
    lh_hrs: "",
    lh_cyc: "",
    rh_hrs: "",
    rh_cyc: "",

    // work
    maintenance_carried_out: "",
    deferred_maintenance: "",
    date_of_completion: "",

    // maintenance data
    amp_used: true,
    amm_used: true,
    mtx_data_used: false,
    amp_reference: "",
    amp_revision: "",
    amp_issue_date: "",
    amm_reference: "",
    amm_revision: "",
    amm_issue_date: "",
    add_mtx_data: "",
    work_order_no: "",

    // expiry
    airframe_limit_unit: defaultUnit as AirframeLimitUnit,
    expiry_date: "",
    hrs_to_expiry: "",
    sum_airframe_tat_expiry: "",
    next_maintenance_due: "",

    // issuer
    issuer_full_name: "",
    issuer_auth_ref: "",
    issuer_license: "",
    crs_issue_date: "",
    crs_issuing_stamp: "",
  });

  const [submitting, setSubmitting] = useState(false);
  const [prefilling, setPrefilling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [prefillError, setPrefillError] = useState<string | null>(null);
  const [successSerial, setSuccessSerial] = useState<string | null>(null);

  const [templateUrl, setTemplateUrl] = useState<string | null>(null);
  const [pdfFields, setPdfFields] = useState<PdfFieldMeta[]>([]);
  const [pdfLoading, setPdfLoading] = useState(true);
  const [pdfError, setPdfError] = useState<string | null>(null);

  // ✅ PDF stage sizing so overlay matches the rendered Page
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [pageWidthPx, setPageWidthPx] = useState<number>(900);

  // Keep the stage height aligned to the rendered PDF page height
  const [pageHeightPx, setPageHeightPx] = useState<number | null>(null);

  useEffect(() => {
    const measure = () => {
      const w = stageRef.current?.clientWidth ?? 0;
      if (w > 0) setPageWidthPx(Math.max(320, w));
    };

    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  // Clean up the blob URL when it changes / unmounts
  useEffect(() => {
    return () => {
      if (templateUrl) URL.revokeObjectURL(templateUrl);
    };
  }, [templateUrl]);

  // Load CRS PDF template + metadata from backend once
  useEffect(() => {
    let cancelled = false;

    const loadTemplate = async () => {
      try {
        setPdfLoading(true);
        setPdfError(null);

        const [pdfBlob, meta]: [Blob, CRSTemplateMeta] = await Promise.all([
          fetchCRSTemplatePdf(),
          fetchCRSTemplateMeta(),
        ]);

        if (cancelled) return;

        const objectUrl = URL.createObjectURL(pdfBlob);
        setTemplateUrl(objectUrl);

        const pages = meta.pages || [];
        const fieldsFromApi = meta.fields || [];

        const firstPage =
          pages.find((p: any) => p.index === 0) || pages[0] || null;

        if (!firstPage) {
          throw new Error("CRS template metadata is missing page size info.");
        }

        const pageWidth = firstPage.width;
        const pageHeight = firstPage.height;

        const mappedFields: PdfFieldMeta[] = fieldsFromApi
          .map((f: any): PdfFieldMeta | null => {
            const pdfName: string = f.name;
            const modelKey = PDF_FIELD_TO_MODEL_KEY[pdfName] ?? null;

            if (!modelKey) return null;

            const x: number = f.x;
            const y: number = f.y;
            const w: number = f.width;
            const h: number = f.height;

            // PDF coords are bottom-left origin. Convert to CSS percentages.
            const leftPct = x / pageWidth;
            const topPct = 1 - (y + h) / pageHeight;
            const widthPct = w / pageWidth;
            const heightPct = h / pageHeight;

            let fieldType: "text" | "checkbox" = "text";
            if (
              pdfName === "AMP" ||
              pdfName === "AMM" ||
              pdfName === "Mtx Data"
            ) {
              fieldType = "checkbox";
            }

            const multiline =
              pdfName === "Maintenance Carried out" ||
              pdfName === "Deferred_Maintenance";

            return {
              pdf_name: pdfName,
              model_key: modelKey,
              page: (f.page_index ?? 0) + 1,
              left_pct: leftPct,
              top_pct: topPct,
              width_pct: widthPct,
              height_pct: heightPct,
              field_type: fieldType,
              multiline,
            };
          })
          .filter(
            (f: PdfFieldMeta | null): f is PdfFieldMeta => !!f && f.page === 1
          );

        setPdfFields(mappedFields);
      } catch (err) {
        console.error("Failed to load CRS template/meta", err);
        if (!cancelled) setPdfError(errMsg(err, "Failed to load CRS template."));
      } finally {
        if (!cancelled) setPdfLoading(false);
      }
    };

    loadTemplate();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleChange = (e: React.ChangeEvent<CRSFieldElement>) => {
    const target = e.target;

    if (target instanceof HTMLInputElement && target.type === "checkbox") {
      const { name, checked } = target;
      setForm((prev) => ({
        ...prev,
        [name]: checked,
      }));
    } else {
      const { name, value } = target;
      setForm((prev) => ({
        ...prev,
        [name]: value,
      }));
    }
  };

  const goBackToDashboard = () => {
    if (amoCode && department) {
      navigate(`/maintenance/${amoCode}/${department}`, { replace: true });
    } else {
      navigate("/login", { replace: true });
    }
  };

  const handlePrefill = async () => {
    setPrefillError(null);
    setError(null);
    setSuccessSerial(null);

    const wo = form.wo_no.trim();
    if (!wo) {
      setPrefillError("Enter a Work Order number, then click Prefill.");
      return;
    }

    try {
      setPrefilling(true);
      const data: CRSPrefill = await prefillCRS(wo);

      setForm((prev) => ({
        ...prev,
        aircraft_serial_number: data.aircraft_serial_number,
        wo_no: data.wo_no,
        releasing_authority:
          (data.releasing_authority as ReleasingAuthority) ??
          prev.releasing_authority,
        operator_contractor: data.operator_contractor ?? prev.operator_contractor,
        job_no: data.job_no ?? prev.job_no,
        location: data.location ?? prev.location,

        aircraft_type: data.aircraft_type ?? prev.aircraft_type,
        aircraft_reg: data.aircraft_reg ?? prev.aircraft_reg,
        msn: data.msn ?? prev.msn,

        lh_engine_type: data.lh_engine_type ?? prev.lh_engine_type,
        rh_engine_type: data.rh_engine_type ?? prev.rh_engine_type,
        lh_engine_sno: data.lh_engine_sno ?? prev.lh_engine_sno,
        rh_engine_sno: data.rh_engine_sno ?? prev.rh_engine_sno,

        aircraft_tat:
          data.aircraft_tat !== undefined && data.aircraft_tat !== null
            ? String(data.aircraft_tat)
            : prev.aircraft_tat,
        aircraft_tac:
          data.aircraft_tac !== undefined && data.aircraft_tac !== null
            ? String(data.aircraft_tac)
            : prev.aircraft_tac,
        lh_hrs:
          data.lh_hrs !== undefined && data.lh_hrs !== null
            ? String(data.lh_hrs)
            : prev.lh_hrs,
        lh_cyc:
          data.lh_cyc !== undefined && data.lh_cyc !== null
            ? String(data.lh_cyc)
            : prev.lh_cyc,
        rh_hrs:
          data.rh_hrs !== undefined && data.rh_hrs !== null
            ? String(data.rh_hrs)
            : prev.rh_hrs,
        rh_cyc:
          data.rh_cyc !== undefined && data.rh_cyc !== null
            ? String(data.rh_cyc)
            : prev.rh_cyc,

        airframe_limit_unit:
          (data.airframe_limit_unit as AirframeLimitUnit) ??
          prev.airframe_limit_unit,
        next_maintenance_due: data.next_maintenance_due ?? prev.next_maintenance_due,
        date_of_completion:
          (data.date_of_completion as string) ?? prev.date_of_completion,
        crs_issue_date: (data.crs_issue_date as string) ?? prev.crs_issue_date,
      }));
    } catch (err) {
      console.error("CRS prefill failed", err);
      setPrefillError("Could not prefill CRS from work order. Check WO number.");
    } finally {
      setPrefilling(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setPrefillError(null);
    setSuccessSerial(null);

    if (!form.wo_no.trim()) return setError("Work Order number is required.");
    if (!form.aircraft_serial_number.trim())
      return setError("Aircraft serial number is required (prefill from WO).");
    if (!form.operator_contractor.trim())
      return setError("Operator / contractor is required.");
    if (!form.location.trim()) return setError("Location is required.");
    if (!form.aircraft_type.trim() || !form.aircraft_reg.trim())
      return setError("Aircraft type and registration are required.");
    if (!form.maintenance_carried_out.trim())
      return setError("Maintenance carried out is required.");
    if (!form.date_of_completion)
      return setError("Date of completion is required.");
    if (
      !form.issuer_full_name.trim() ||
      !form.issuer_auth_ref.trim() ||
      !form.issuer_license.trim()
    ) {
      return setError("Issuer name, authorization ref, and licence are required.");
    }
    if (!form.crs_issue_date) return setError("CRS issue date is required.");

    const payload: CRSCreate = {
      aircraft_serial_number: form.aircraft_serial_number.trim(),
      wo_no: form.wo_no.trim(),

      releasing_authority: form.releasing_authority,
      operator_contractor: form.operator_contractor.trim(),
      job_no: form.job_no.trim() || undefined,
      location: form.location.trim(),

      aircraft_type: form.aircraft_type.trim(),
      aircraft_reg: form.aircraft_reg.trim(),
      msn: form.msn.trim() || undefined,

      lh_engine_type: form.lh_engine_type.trim() || undefined,
      rh_engine_type: form.rh_engine_type.trim() || undefined,
      lh_engine_sno: form.lh_engine_sno.trim() || undefined,
      rh_engine_sno: form.rh_engine_sno.trim() || undefined,

      aircraft_tat: form.aircraft_tat ? Number(form.aircraft_tat) : undefined,
      aircraft_tac: form.aircraft_tac ? Number(form.aircraft_tac) : undefined,
      lh_hrs: form.lh_hrs ? Number(form.lh_hrs) : undefined,
      lh_cyc: form.lh_cyc ? Number(form.lh_cyc) : undefined,
      rh_hrs: form.rh_hrs ? Number(form.rh_hrs) : undefined,
      rh_cyc: form.rh_cyc ? Number(form.rh_cyc) : undefined,

      maintenance_carried_out: form.maintenance_carried_out.trim(),
      deferred_maintenance: form.deferred_maintenance.trim() || undefined,
      date_of_completion: form.date_of_completion,

      amp_used: form.amp_used,
      amm_used: form.amm_used,
      mtx_data_used: form.mtx_data_used,

      amp_reference: form.amp_reference.trim() || undefined,
      amp_revision: form.amp_revision.trim() || undefined,
      amp_issue_date: form.amp_issue_date || undefined,

      amm_reference: form.amm_reference.trim() || undefined,
      amm_revision: form.amm_revision.trim() || undefined,
      amm_issue_date: form.amm_issue_date || undefined,

      add_mtx_data: form.add_mtx_data.trim() || undefined,
      work_order_no: form.work_order_no.trim() || form.wo_no.trim(),

      airframe_limit_unit: form.airframe_limit_unit,
      expiry_date: form.expiry_date || undefined,
      hrs_to_expiry: form.hrs_to_expiry ? Number(form.hrs_to_expiry) : undefined,
      sum_airframe_tat_expiry: form.sum_airframe_tat_expiry
        ? Number(form.sum_airframe_tat_expiry)
        : undefined,
      next_maintenance_due: form.next_maintenance_due.trim() || undefined,

      issuer_full_name: form.issuer_full_name.trim(),
      issuer_auth_ref: form.issuer_auth_ref.trim(),
      issuer_license: form.issuer_license.trim(),
      crs_issue_date: form.crs_issue_date,
      crs_issuing_stamp: form.crs_issuing_stamp.trim() || undefined,

      signoffs: [],
    };

    try {
      setSubmitting(true);
      const created = await createCRS(payload);
      setSuccessSerial(created.crs_serial);
    } catch (err) {
      console.error("CRS create failed", err);
      setError(errMsg(err, "Failed to create CRS."));
    } finally {
      setSubmitting(false);
    }
  };

  const renderPdfField = (field: PdfFieldMeta) => {
    if (!field.model_key) return null;

    const value = (form as any)[field.model_key] ?? "";

    const style: React.CSSProperties = {
      position: "absolute",
      left: `${field.left_pct * 100}%`,
      top: `${field.top_pct * 100}%`,
      width: `${field.width_pct * 100}%`,
      height: `${field.height_pct * 100}%`,
      boxSizing: "border-box",
    };

    if (field.field_type === "checkbox") {
      return (
        <label
          key={field.pdf_name}
          className="crs-pdf-checkbox-wrapper"
          style={style}
        >
          <input
            type="checkbox"
            name={field.model_key}
            checked={!!(form as any)[field.model_key]}
            onChange={handleChange}
            className="crs-pdf-checkbox"
          />
        </label>
      );
    }

    if (field.multiline) {
      return (
        <textarea
          key={field.pdf_name}
          name={field.model_key}
          value={value}
          onChange={handleChange}
          className="crs-pdf-input crs-pdf-textarea"
          style={style}
        />
      );
    }

    return (
      <input
        key={field.pdf_name}
        type="text"
        name={field.model_key}
        value={value}
        onChange={handleChange}
        className="crs-pdf-input"
        style={style}
      />
    );
  };

  return (
    <DepartmentLayout amoCode={amoCode ?? ""} activeDepartment={department ?? ""}>
      <section className="dept-panel">
        <header className="dept-panel__header">
          <div>
            <h1>New CRS</h1>
            <p>
              Fill the official CRS form on-screen. The layout matches the
              current PDF template.
            </p>
          </div>
          <button
            type="button"
            className="primary-chip-btn"
            onClick={goBackToDashboard}
          >
            ← Back to dashboard
          </button>
        </header>

        <div className="dept-panel__body crs-panel">
          <form className="crs-form" onSubmit={handleSubmit}>
            {error && <div className="auth-form__error">{error}</div>}
            {prefillError && <div className="auth-form__error">{prefillError}</div>}
            {pdfError && <div className="auth-form__error">{pdfError}</div>}
            {successSerial && (
              <div className="auth-form__success">
                CRS <strong>{successSerial}</strong> created. You can later
                download the PDF from the CRS list.
              </div>
            )}

            <div className="crs-form__top-row">
              <label className="auth-form__label">
                WO no.
                <div className="crs-form__wo-prefill-row">
                  <input
                    type="text"
                    name="wo_no"
                    value={form.wo_no}
                    onChange={handleChange}
                    className="auth-form__input"
                  />
                  <button
                    type="button"
                    className="secondary-btn"
                    onClick={handlePrefill}
                    disabled={prefilling}
                  >
                    {prefilling ? "Prefilling..." : "Prefill from WO"}
                  </button>
                </div>
              </label>

              <label className="auth-form__label">
                Aircraft serial (WinAir)
                <input
                  type="text"
                  name="aircraft_serial_number"
                  value={form.aircraft_serial_number}
                  onChange={handleChange}
                  className="auth-form__input"
                  readOnly
                />
              </label>
            </div>

            <div className="crs-form__authority-row">
              <label className="auth-form__label">
                Releasing authority
                <select
                  name="releasing_authority"
                  value={form.releasing_authority}
                  onChange={handleChange}
                  className="auth-form__input"
                >
                  <option value="KCAA">KCAA</option>
                  <option value="FAA">FAA</option>
                  <option value="EASA">EASA</option>
                  <option value="OTHER">Other</option>
                </select>
              </label>
            </div>

            <div className="crs-pdf-wrapper">
              {pdfLoading && <p className="crs-pdf-status">Loading CRS template…</p>}

              {/* ✅ Stage container: PDF + overlay share the same coordinate space */}
              <div
                className="crs-pdf-stage"
                ref={stageRef}
                style={{
                  position: "relative",
                  width: "100%",
                  height: pageHeightPx ? `${pageHeightPx}px` : "auto",
                }}
              >
                {templateUrl && (
                  <PdfDocument
                    file={templateUrl}
                    className="crs-pdf-document"
                    loading={<p className="crs-pdf-status">Rendering CRS template…</p>}
                    error={<p className="crs-pdf-status">Failed to render CRS template.</p>}
                    onLoadError={(e: unknown) => {
                      console.error("PDF load error:", e);
                      setPdfError(errMsg(e, "Failed to load CRS PDF."));
                    }}
                  >
                    <PdfPage
                      pageNumber={1}
                      width={pageWidthPx}
                      renderAnnotationLayer={false}
                      renderTextLayer={false}
                      className="crs-pdf-page"
                      onLoadSuccess={(page: any) => {
                        try {
                          const vp = page.getViewport({ scale: 1 });
                          const scale = pageWidthPx / vp.width;
                          setPageHeightPx(vp.height * scale);
                        } catch (e) {
                          console.warn("Could not compute PDF viewport:", e);
                        }
                      }}
                      onRenderError={(e: unknown) => {
                        console.error("PDF render error:", e);
                        setPdfError(errMsg(e, "Failed to render CRS template."));
                      }}
                    />
                  </PdfDocument>
                )}

                <div
                  className="crs-pdf-overlay"
                  style={{
                    position: "absolute",
                    inset: 0,
                    pointerEvents: "auto",
                  }}
                >
                  {pdfFields.map((f) => renderPdfField(f))}
                </div>
              </div>
            </div>

            <div className="auth-form__actions crs-form__actions">
              <button
                type="button"
                className="secondary-btn"
                onClick={goBackToDashboard}
                disabled={submitting}
              >
                Cancel
              </button>
              <button type="submit" className="primary-btn" disabled={submitting}>
                {submitting ? "Saving..." : "Save CRS"}
              </button>
            </div>
          </form>
        </div>
      </section>
    </DepartmentLayout>
  );
};

export default CRSNewPage;
