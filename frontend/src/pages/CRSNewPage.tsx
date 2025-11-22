// src/pages/CRSNewPage.tsx
import React, { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import type {
  CRSCreate,
  ReleasingAuthority,
  AirframeLimitUnit,
  CRSPrefill,
} from "../types/crs";
import { createCRS, prefillCRS } from "../services/crs";

const defaultReleasing: ReleasingAuthority = "KCAA";
const defaultUnit: AirframeLimitUnit = "HOURS";

type CRSFieldElement = HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;

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
        releasing_authority: data.releasing_authority ?? prev.releasing_authority,
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
          data.airframe_limit_unit ?? prev.airframe_limit_unit,
        next_maintenance_due:
          data.next_maintenance_due ?? prev.next_maintenance_due,
        date_of_completion:
          data.date_of_completion ?? prev.date_of_completion,
        crs_issue_date: data.crs_issue_date ?? prev.crs_issue_date,
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

    if (!form.wo_no.trim()) {
      setError("Work Order number is required.");
      return;
    }
    if (!form.aircraft_serial_number.trim()) {
      setError("Aircraft serial number is required (prefill from WO).");
      return;
    }
    if (!form.operator_contractor.trim()) {
      setError("Operator / contractor is required.");
      return;
    }
    if (!form.location.trim()) {
      setError("Location is required.");
      return;
    }
    if (!form.aircraft_type.trim() || !form.aircraft_reg.trim()) {
      setError("Aircraft type and registration are required.");
      return;
    }
    if (!form.maintenance_carried_out.trim()) {
      setError("Maintenance carried out is required.");
      return;
    }
    if (!form.date_of_completion) {
      setError("Date of completion is required.");
      return;
    }
    if (
      !form.issuer_full_name.trim() ||
      !form.issuer_auth_ref.trim() ||
      !form.issuer_license.trim()
    ) {
      setError("Issuer name, authorization ref, and licence are required.");
      return;
    }
    if (!form.crs_issue_date) {
      setError("CRS issue date is required.");
      return;
    }

    const payload: CRSCreate = {
      // linkage
      aircraft_serial_number: form.aircraft_serial_number.trim(),
      wo_no: form.wo_no.trim(),

      // header
      releasing_authority: form.releasing_authority,
      operator_contractor: form.operator_contractor.trim(),
      job_no: form.job_no.trim() || undefined,
      location: form.location.trim(),

      // aircraft & engines
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

      // work
      maintenance_carried_out: form.maintenance_carried_out.trim(),
      deferred_maintenance: form.deferred_maintenance.trim() || undefined,
      date_of_completion: form.date_of_completion,

      // maintenance data
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

      // expiry
      airframe_limit_unit: form.airframe_limit_unit,
      expiry_date: form.expiry_date || undefined,
      hrs_to_expiry: form.hrs_to_expiry
        ? Number(form.hrs_to_expiry)
        : undefined,
      sum_airframe_tat_expiry: form.sum_airframe_tat_expiry
        ? Number(form.sum_airframe_tat_expiry)
        : undefined,
      next_maintenance_due:
        form.next_maintenance_due.trim() || undefined,

      // issuer
      issuer_full_name: form.issuer_full_name.trim(),
      issuer_auth_ref: form.issuer_auth_ref.trim(),
      issuer_license: form.issuer_license.trim(),
      crs_issue_date: form.crs_issue_date,
      crs_issuing_stamp: form.crs_issuing_stamp.trim() || undefined,

      // sign-offs (v1)
      signoffs: [],
    };

    try {
      setSubmitting(true);
      const created = await createCRS(payload);
      setSuccessSerial(created.crs_serial);
    } catch (err) {
      console.error("CRS create failed", err);
      if (err instanceof Error) {
        setError(err.message || "Failed to create CRS.");
      } else {
        setError("Failed to create CRS.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const formatDate = (value: string | undefined) => (value ? value : "—");

  return (
    <DepartmentLayout
      amoCode={amoCode ?? ""}
      activeDepartment={department ?? ""}
    >
      <section className="dept-panel">
        <header className="dept-panel__header">
          <div>
            <h1>New CRS</h1>
            <p>Create a new Certificate of Release to Service entry.</p>
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
          {/* LEFT: FORM */}
          <form className="crs-form" onSubmit={handleSubmit}>
            {error && <div className="auth-form__error">{error}</div>}
            {prefillError && (
              <div className="auth-form__error">{prefillError}</div>
            )}
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

            <div className="crs-form__grid">
              {/* Column 1 – header & aircraft */}
              <div className="crs-form__section">
                <h2>Header</h2>

                <label className="auth-form__label">
                  Releasing authority
                  <select
                    name="releasing_authority"
                    value={form.releasing_authority}
                    onChange={handleChange}
                    className="auth-form__input"
                  >
                    <option value="KCAA">KCAA</option>
                    <option value="ECAA">ECAA</option>
                    <option value="GCAA">GCAA</option>
                  </select>
                </label>

                <label className="auth-form__label">
                  Operator / contractor
                  <input
                    type="text"
                    name="operator_contractor"
                    value={form.operator_contractor}
                    onChange={handleChange}
                    className="auth-form__input"
                  />
                </label>

                <div className="crs-form__row">
                  <label className="auth-form__label">
                    Job no.
                    <input
                      type="text"
                      name="job_no"
                      value={form.job_no}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                  <label className="auth-form__label">
                    Location
                    <input
                      type="text"
                      name="location"
                      value={form.location}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                </div>

                <h2>Aircraft</h2>
                <div className="crs-form__row">
                  <label className="auth-form__label">
                    Aircraft type
                    <input
                      type="text"
                      name="aircraft_type"
                      value={form.aircraft_type}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>

                  <label className="auth-form__label">
                    Registration
                    <input
                      type="text"
                      name="aircraft_reg"
                      value={form.aircraft_reg}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>

                  <label className="auth-form__label">
                    MSN
                    <input
                      type="text"
                      name="msn"
                      value={form.msn}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                </div>

                <h3>Engines</h3>
                <div className="crs-form__row">
                  <label className="auth-form__label">
                    LH engine type
                    <input
                      type="text"
                      name="lh_engine_type"
                      value={form.lh_engine_type}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                  <label className="auth-form__label">
                    LH engine S/N
                    <input
                      type="text"
                      name="lh_engine_sno"
                      value={form.lh_engine_sno}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                </div>
                <div className="crs-form__row">
                  <label className="auth-form__label">
                    RH engine type
                    <input
                      type="text"
                      name="rh_engine_type"
                      value={form.rh_engine_type}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                  <label className="auth-form__label">
                    RH engine S/N
                    <input
                      type="text"
                      name="rh_engine_sno"
                      value={form.rh_engine_sno}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                </div>

                <h3>Utilisation snapshot</h3>
                <div className="crs-form__row">
                  <label className="auth-form__label">
                    Aircraft TAT (hrs)
                    <input
                      type="number"
                      name="aircraft_tat"
                      value={form.aircraft_tat}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                  <label className="auth-form__label">
                    Aircraft TAC (cyc)
                    <input
                      type="number"
                      name="aircraft_tac"
                      value={form.aircraft_tac}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                </div>
                <div className="crs-form__row">
                  <label className="auth-form__label">
                    LH hrs
                    <input
                      type="number"
                      name="lh_hrs"
                      value={form.lh_hrs}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                  <label className="auth-form__label">
                    LH cyc
                    <input
                      type="number"
                      name="lh_cyc"
                      value={form.lh_cyc}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                </div>
                <div className="crs-form__row">
                  <label className="auth-form__label">
                    RH hrs
                    <input
                      type="number"
                      name="rh_hrs"
                      value={form.rh_hrs}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                  <label className="auth-form__label">
                    RH cyc
                    <input
                      type="number"
                      name="rh_cyc"
                      value={form.rh_cyc}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                </div>
              </div>

              {/* Column 2 – work & data */}
              <div className="crs-form__section">
                <h2>Work performed</h2>
                <label className="auth-form__label">
                  Maintenance carried out
                  <textarea
                    name="maintenance_carried_out"
                    value={form.maintenance_carried_out}
                    onChange={handleChange}
                    className="auth-form__textarea"
                    rows={6}
                  />
                </label>

                <label className="auth-form__label">
                  Deferred maintenance
                  <textarea
                    name="deferred_maintenance"
                    value={form.deferred_maintenance}
                    onChange={handleChange}
                    className="auth-form__textarea"
                    rows={3}
                  />
                </label>

                <label className="auth-form__label">
                  Date of completion
                  <input
                    type="date"
                    name="date_of_completion"
                    value={form.date_of_completion}
                    onChange={handleChange}
                    className="auth-form__input"
                  />
                </label>

                <h2>Maintenance data</h2>
                <div className="crs-form__row crs-form__row--checkboxes">
                  <label className="auth-form__checkbox">
                    <input
                      type="checkbox"
                      name="amp_used"
                      checked={form.amp_used}
                      onChange={handleChange}
                    />
                    AMP used
                  </label>
                  <label className="auth-form__checkbox">
                    <input
                      type="checkbox"
                      name="amm_used"
                      checked={form.amm_used}
                      onChange={handleChange}
                    />
                    AMM used
                  </label>
                  <label className="auth-form__checkbox">
                    <input
                      type="checkbox"
                      name="mtx_data_used"
                      checked={form.mtx_data_used}
                      onChange={handleChange}
                    />
                    Additional maintenance data
                  </label>
                </div>

                <div className="crs-form__row">
                  <label className="auth-form__label">
                    AMP reference
                    <input
                      type="text"
                      name="amp_reference"
                      value={form.amp_reference}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                  <label className="auth-form__label">
                    AMP revision
                    <input
                      type="text"
                      name="amp_revision"
                      value={form.amp_revision}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                </div>

                <div className="crs-form__row">
                  <label className="auth-form__label">
                    AMP issue date
                    <input
                      type="date"
                      name="amp_issue_date"
                      value={form.amp_issue_date}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                </div>

                <div className="crs-form__row">
                  <label className="auth-form__label">
                    AMM reference
                    <input
                      type="text"
                      name="amm_reference"
                      value={form.amm_reference}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                  <label className="auth-form__label">
                    AMM revision
                    <input
                      type="text"
                      name="amm_revision"
                      value={form.amm_revision}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                </div>

                <div className="crs-form__row">
                  <label className="auth-form__label">
                    AMM issue date
                    <input
                      type="date"
                      name="amm_issue_date"
                      value={form.amm_issue_date}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                </div>

                <label className="auth-form__label">
                  Additional maintenance data
                  <input
                    type="text"
                    name="add_mtx_data"
                    value={form.add_mtx_data}
                    onChange={handleChange}
                    className="auth-form__input"
                  />
                </label>

                <label className="auth-form__label">
                  Work order no. (alternate)
                  <input
                    type="text"
                    name="work_order_no"
                    value={form.work_order_no}
                    onChange={handleChange}
                    className="auth-form__input"
                  />
                </label>
              </div>

              {/* Column 3 – expiry & issuing details */}
              <div className="crs-form__section">
                <h2>Expiry / next maintenance</h2>
                <div className="crs-form__row">
                  <label className="auth-form__label">
                    Unit
                    <select
                      name="airframe_limit_unit"
                      value={form.airframe_limit_unit}
                      onChange={handleChange}
                      className="auth-form__input"
                    >
                      <option value="HOURS">Hours</option>
                      <option value="CYCLES">Cycles</option>
                    </select>
                  </label>

                  <label className="auth-form__label">
                    Expiry date
                    <input
                      type="date"
                      name="expiry_date"
                      value={form.expiry_date}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                </div>

                <div className="crs-form__row">
                  <label className="auth-form__label">
                    Hours / cycles to expiry
                    <input
                      type="number"
                      name="hrs_to_expiry"
                      value={form.hrs_to_expiry}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                  <label className="auth-form__label">
                    SUM (TAT + to expiry)
                    <input
                      type="number"
                      name="sum_airframe_tat_expiry"
                      value={form.sum_airframe_tat_expiry}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                </div>

                <label className="auth-form__label">
                  Next maintenance due
                  <input
                    type="text"
                    name="next_maintenance_due"
                    value={form.next_maintenance_due}
                    onChange={handleChange}
                    className="auth-form__input"
                  />
                </label>

                <h2>Certificate issued by</h2>
                <label className="auth-form__label">
                  Full name
                  <input
                    type="text"
                    name="issuer_full_name"
                    value={form.issuer_full_name}
                    onChange={handleChange}
                    className="auth-form__input"
                  />
                </label>

                <div className="crs-form__row">
                  <label className="auth-form__label">
                    Internal authorization ref
                    <input
                      type="text"
                      name="issuer_auth_ref"
                      value={form.issuer_auth_ref}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                  <label className="auth-form__label">
                    Category (A&C) licence
                    <input
                      type="text"
                      name="issuer_license"
                      value={form.issuer_license}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                </div>

                <label className="auth-form__label">
                  CRS issue date
                  <input
                    type="date"
                    name="crs_issue_date"
                    value={form.crs_issue_date}
                    onChange={handleChange}
                    className="auth-form__input"
                  />
                </label>

                <label className="auth-form__label">
                  CRS issuing stamp / code
                  <input
                    type="text"
                    name="crs_issuing_stamp"
                    value={form.crs_issuing_stamp}
                    onChange={handleChange}
                    className="auth-form__input"
                  />
                </label>
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
              <button
                type="submit"
                className="primary-btn"
                disabled={submitting}
              >
                {submitting ? "Saving..." : "Save CRS"}
              </button>
            </div>
          </form>

          {/* RIGHT: LIVE PREVIEW */}
          <aside className="crs-preview">
            <h2>CRS Preview (live)</h2>
            <p className="crs-preview__line">
              <strong>Authority:</strong> {form.releasing_authority}
            </p>
            <p className="crs-preview__line">
              <strong>Operator:</strong> {form.operator_contractor || "—"}
            </p>
            <p className="crs-preview__line">
              <strong>WO:</strong> {form.wo_no || "—"}{" "}
              <strong>Job:</strong> {form.job_no || "—"}
            </p>
            <p className="crs-preview__line">
              <strong>Location:</strong> {form.location || "—"}
            </p>

            <hr />

            <p className="crs-preview__line">
              <strong>Aircraft:</strong>{" "}
              {form.aircraft_reg || "—"} ({form.aircraft_type || "—"})
            </p>
            <p className="crs-preview__line">
              <strong>MSN:</strong> {form.msn || "—"} |{" "}
              <strong>Serial:</strong> {form.aircraft_serial_number || "—"}
            </p>

            <p className="crs-preview__line">
              <strong>TAT/TAC:</strong>{" "}
              {form.aircraft_tat || "0"} hrs / {form.aircraft_tac || "0"} cyc
            </p>

            <p className="crs-preview__line">
              <strong>LH:</strong> {form.lh_engine_type || "—"} S/N{" "}
              {form.lh_engine_sno || "—"} ({form.lh_hrs || "0"} hrs /{" "}
              {form.lh_cyc || "0"} cyc)
            </p>
            <p className="crs-preview__line">
              <strong>RH:</strong> {form.rh_engine_type || "—"} S/N{" "}
              {form.rh_engine_sno || "—"} ({form.rh_hrs || "0"} hrs /{" "}
              {form.rh_cyc || "0"} cyc)
            </p>

            <hr />

            <p className="crs-preview__line">
              <strong>Maintenance carried out:</strong>
            </p>
            <p className="crs-preview__multiline">
              {form.maintenance_carried_out || "—"}
            </p>

            {form.deferred_maintenance && (
              <>
                <p className="crs-preview__line">
                  <strong>Deferred maintenance:</strong>
                </p>
                <p className="crs-preview__multiline">
                  {form.deferred_maintenance}
                </p>
              </>
            )}

            <p className="crs-preview__line">
              <strong>Date of completion:</strong>{" "}
              {formatDate(form.date_of_completion)}
            </p>

            <hr />

            <p className="crs-preview__line">
              <strong>Next due:</strong>{" "}
              {form.next_maintenance_due || "—"} (
              {form.airframe_limit_unit === "HOURS" ? "Hrs" : "Cycles"})
            </p>
            <p className="crs-preview__line">
              <strong>To expiry:</strong>{" "}
              {form.hrs_to_expiry || "0"} / Sum{" "}
              {form.sum_airframe_tat_expiry || "0"}
            </p>
            <p className="crs-preview__line">
              <strong>Expiry date:</strong>{" "}
              {formatDate(form.expiry_date)}
            </p>

            <hr />

            <p className="crs-preview__line">
              <strong>Issuer:</strong> {form.issuer_full_name || "—"} (
              {form.issuer_license || "—"})
            </p>
            <p className="crs-preview__line">
              <strong>Auth ref:</strong> {form.issuer_auth_ref || "—"}
            </p>
            <p className="crs-preview__line">
              <strong>CRS issue date:</strong>{" "}
              {formatDate(form.crs_issue_date)}
            </p>
          </aside>
        </div>
      </section>
    </DepartmentLayout>
  );
};

export default CRSNewPage;
