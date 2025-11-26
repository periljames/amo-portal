// src/pages/AdminUserNewPage.tsx
import React, { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { createAdminUser } from "../services/adminUsers";
import type {
  AdminUserCreatePayload,
  AccountRole,
} from "../services/adminUsers";

type UrlParams = {
  amoCode?: string;
  department?: string;
};

const DEFAULT_ROLE: AccountRole = "AMO_ADMIN";

const AdminUserNewPage: React.FC = () => {
  const navigate = useNavigate();
  const { amoCode, department } = useParams<UrlParams>();

  const [form, setForm] = useState({
    staffCode: "",
    firstName: "",
    lastName: "",
    email: "",
    role: DEFAULT_ROLE as AccountRole,
    positionTitle: "",
    phone: "",
    password: "",
    confirmPassword: "",
  });

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => {
    const { name, value } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!form.password || form.password !== form.confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    if (!form.email.trim() || !form.staffCode.trim()) {
      setError("Email and staff code are required.");
      return;
    }

    setSubmitting(true);
    try {
      const payload: AdminUserCreatePayload = {
        staff_code: form.staffCode.trim().toUpperCase(),
        email: form.email.trim().toLowerCase(),
        first_name: form.firstName.trim(),
        last_name: form.lastName.trim(),
        full_name: `${form.firstName.trim()} ${form.lastName.trim()}`.trim(),
        role: form.role,
        position_title: form.positionTitle.trim() || undefined,
        phone: form.phone.trim() || undefined,
        password: form.password,
        // department_id, regulatory fields, licences, etc.
        // can be added here later if you want.
      };

      await createAdminUser(payload);

      setSuccess("User created successfully.");
      const target =
        amoCode && department
          ? `/maintenance/${amoCode}/${department}`
          : "/login";
      setTimeout(() => {
        navigate(target);
      }, 800);
    } catch (err: any) {
      console.error("Failed to create user", err);
      const msg =
        err?.response?.data?.detail ||
        err?.message ||
        "Failed to create user. Please try again.";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const pageTitle =
    amoCode && department
      ? `Create User – ${amoCode.toUpperCase()} / ${department}`
      : "Create User";

  return (
    <div className="page-root">
      <div className="page-header">
        <h1>{pageTitle}</h1>
        <p className="page-subtitle">
          Create a new AMO user (AMO admin or other staff). The AMO will be
          taken from your current login.
        </p>
      </div>

      <div className="card card--form">
        <form onSubmit={handleSubmit} className="form-grid">
          {error && <div className="alert alert-error">{error}</div>}
          {success && <div className="alert alert-success">{success}</div>}

          <div className="form-row">
            <label htmlFor="staffCode">Staff Code</label>
            <input
              id="staffCode"
              name="staffCode"
              type="text"
              value={form.staffCode}
              onChange={handleChange}
              autoComplete="off"
              required
            />
          </div>

          <div className="form-row">
            <label htmlFor="firstName">First Name</label>
            <input
              id="firstName"
              name="firstName"
              type="text"
              value={form.firstName}
              onChange={handleChange}
              autoComplete="off"
              required
            />
          </div>

          <div className="form-row">
            <label htmlFor="lastName">Last Name</label>
            <input
              id="lastName"
              name="lastName"
              type="text"
              value={form.lastName}
              onChange={handleChange}
              autoComplete="off"
              required
            />
          </div>

          <div className="form-row">
            <label htmlFor="email">Work Email</label>
            <input
              id="email"
              name="email"
              type="email"
              value={form.email}
              onChange={handleChange}
              autoComplete="off"
              required
            />
          </div>

          <div className="form-row">
            <label htmlFor="role">Role</label>
            <select
              id="role"
              name="role"
              value={form.role}
              onChange={handleChange}
            >
              <option value="AMO_ADMIN">AMO Admin</option>
              <option value="QUALITY_MANAGER">Quality Manager</option>
              <option value="SAFETY_MANAGER">Safety Manager</option>
              <option value="CERTIFYING_ENGINEER">Certifying Engineer</option>
              <option value="CERTIFYING_TECHNICIAN">
                Certifying Technician
              </option>
              <option value="TECHNICIAN">Technician</option>
              <option value="STORES">Stores</option>
              <option value="VIEW_ONLY">View Only</option>
              <option value="SUPERUSER">Platform Superuser</option>
            </select>
          </div>

          <div className="form-row">
            <label htmlFor="positionTitle">Position Title</label>
            <input
              id="positionTitle"
              name="positionTitle"
              type="text"
              value={form.positionTitle}
              onChange={handleChange}
              placeholder="e.g. Maintenance Manager"
            />
          </div>

          <div className="form-row">
            <label htmlFor="phone">Phone</label>
            <input
              id="phone"
              name="phone"
              type="tel"
              value={form.phone}
              onChange={handleChange}
              placeholder="+254..."
            />
          </div>

          <div className="form-row">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              name="password"
              type="password"
              value={form.password}
              onChange={handleChange}
              required
            />
          </div>

          <div className="form-row">
            <label htmlFor="confirmPassword">Confirm Password</label>
            <input
              id="confirmPassword"
              name="confirmPassword"
              type="password"
              value={form.confirmPassword}
              onChange={handleChange}
              required
            />
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                const target =
                  amoCode && department
                    ? `/maintenance/${amoCode}/${department}`
                    : "/login";
                navigate(target);
              }}
              disabled={submitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting}
            >
              {submitting ? "Creating..." : "Create User"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default AdminUserNewPage;
