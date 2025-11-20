// src/pages/CRSNewPage.tsx
import React, { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import type { CRSCreate, ReleasingAuthority, AirframeLimitUnit } from "../types/crs";
import { createCRS } from "../services/apis/crs";

const defaultReleasing: ReleasingAuthority = "KCAA";
const defaultUnit: AirframeLimitUnit = "HOURS";

const CRSNewPage: React.FC = () => {
  const navigate = useNavigate();
  const { amoCode = "safa03", department = "planning" } = useParams<{
    amoCode: string;
    department: string;
  }>();

  const [form, setForm] = useState({
    releasing_authority: defaultReleasing as ReleasingAuthority,
    operator_contractor: "Safarilink Aviation Ltd",
    job_no: "",
    wo_no: "",
    location: "HKNA",
    aircraft_type: "",
    aircraft_reg: "",
    msn: "",
    maintenance_carried_out: "",
    deferred_maintenance: "",
    date_of_completion: "",
    amp_used: true,
    amm_used: true,
    mtx_data_used: false,
    amp_reference: "",
    amm_reference: "",
    airframe_limit_unit: defaultUnit as AirframeLimitUnit,
    expiry_date: "",
    hrs_to_expiry: "",
    next_maintenance_due: "",
    issuer_full_name: "",
    issuer_auth_ref: "",
    issuer_license: "",
    crs_issue_date: "",
  });

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successSerial, setSuccessSerial] = useState<string | null>(null);
  
  const handleChange = (
    e: React.ChangeEvent<
      HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
    >
  ) => {
    const { name, value, type } = e.target;

    if (type === "checkbox") {
    const input = e.target as HTMLInputElement;
    setForm((prev) => ({
      ...prev,
      [name]: input.checked,
      }));
    } else {
    setForm((prev) => ({
      ...prev,
      [name]: value,
     }));
   }
  };

  const goBackToDashboard = () => {
    navigate(`/maintenance.${amoCode}/${department}`);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessSerial(null);

    // Minimal validation for mandatory backend fields
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
      // header
      releasing_authority: form.releasing_authority,
      operator_contractor: form.operator_contractor.trim(),
      job_no: form.job_no.trim() || undefined,
      wo_no: form.wo_no.trim() || undefined,
      location: form.location.trim(),

      // aircraft
      aircraft_type: form.aircraft_type.trim(),
      aircraft_reg: form.aircraft_reg.trim(),
      msn: form.msn.trim() || undefined,

      // (engines + counters skipped for v1)
      maintenance_carried_out: form.maintenance_carried_out.trim(),
      deferred_maintenance: form.deferred_maintenance.trim() || undefined,
      date_of_completion: form.date_of_completion,

      amp_used: form.amp_used,
      amm_used: form.amm_used,
      mtx_data_used: form.mtx_data_used,

      amp_reference: form.amp_reference.trim() || undefined,
      amm_reference: form.amm_reference.trim() || undefined,

      airframe_limit_unit: form.airframe_limit_unit,
      expiry_date: form.expiry_date || undefined,
      hrs_to_expiry: form.hrs_to_expiry
        ? Number(form.hrs_to_expiry)
        : undefined,
      next_maintenance_due: form.next_maintenance_due.trim() || undefined,

      issuer_full_name: form.issuer_full_name.trim(),
      issuer_auth_ref: form.issuer_auth_ref.trim(),
      issuer_license: form.issuer_license.trim(),
      crs_issue_date: form.crs_issue_date,

      // v1: no sign-offs yet
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

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment={department}>
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

        <div className="dept-panel__body">
          <form className="crs-form" onSubmit={handleSubmit}>
            {error && <div className="auth-form__error">{error}</div>}
            {successSerial && (
              <div className="auth-form__success">
                CRS <strong>{successSerial}</strong> created. You can later
                download the PDF from the CRS list.
              </div>
            )}

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
                    WO no.
                    <input
                      type="text"
                      name="wo_no"
                      value={form.wo_no}
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
                    AMM reference
                    <input
                      type="text"
                      name="amm_reference"
                      value={form.amm_reference}
                      onChange={handleChange}
                      className="auth-form__input"
                    />
                  </label>
                </div>
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
        </div>
      </section>
    </DepartmentLayout>
  );
};

export default CRSNewPage;
