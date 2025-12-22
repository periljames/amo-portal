// src/pages/AdminUserNewPage.tsx
import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { createAdminUser } from "../services/adminUsers";
import type { AdminUserCreatePayload, AccountRole } from "../services/adminUsers";
import { getCachedUser, getContext } from "../services/auth";

type UrlParams = {
  amoCode?: string;
};

const DEFAULT_ROLE: AccountRole = "AMO_ADMIN";

const ROLE_OPTIONS: Array<{ value: AccountRole; label: string }> = [
  { value: "AMO_ADMIN", label: "AMO Admin" },
  { value: "QUALITY_MANAGER", label: "Quality Manager" },
  { value: "SAFETY_MANAGER", label: "Safety Manager" },
  { value: "PLANNING_ENGINEER", label: "Planning Engineer" },
  { value: "PRODUCTION_ENGINEER", label: "Production Engineer" },
  { value: "CERTIFYING_ENGINEER", label: "Certifying Engineer" },
  { value: "CERTIFYING_TECHNICIAN", label: "Certifying Technician" },
  { value: "TECHNICIAN", label: "Technician" },
  { value: "STORES", label: "Stores" },
  { value: "VIEW_ONLY", label: "View Only" },
  { value: "SUPERUSER", label: "Platform Superuser" },
];

const AdminUserNewPage: React.FC = () => {
  const navigate = useNavigate();
  const { amoCode } = useParams<UrlParams>();

  const ctx = getContext();
  const currentUser = getCachedUser();

  const isAdmin = useMemo(() => {
    if (!currentUser) return false;
    return currentUser.role === "SUPERUSER" || currentUser.role === "AMO_ADMIN";
  }, [currentUser]);

  const isSuperuser = !!currentUser?.is_superuser;

  const backTarget = useMemo(() => {
    const slug = amoCode ?? ctx.amoCode ?? null;
    return slug ? `/maintenance/${slug}/admin/users` : "/login";
  }, [amoCode, ctx.amoCode]);

  const pageTitle = useMemo(() => {
    const slug = amoCode ?? ctx.amoCode ?? "UNKNOWN";
    return `Create User – ${slug.toUpperCase()}`;
  }, [amoCode, ctx.amoCode]);

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
  const [showPassword, setShowPassword] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const validate = (): string | null => {
    const staff = form.staffCode.trim();
    const email = form.email.trim();

    if (!staff) return "Staff code is required.";
    if (!email) return "Email is required.";
    if (!form.firstName.trim() || !form.lastName.trim()) {
      return "First name and last name are required.";
    }

    if (!form.password) return "Password is required.";
    if (form.password !== form.confirmPassword) return "Passwords do not match.";

    if (form.password.length < 12) {
      return "Password must be at least 12 characters.";
    }
    const hasUpper = /[A-Z]/.test(form.password);
    const hasLower = /[a-z]/.test(form.password);
    const hasDigit = /\d/.test(form.password);
    const hasSymbol = /[^A-Za-z0-9]/.test(form.password);
    if (!(hasUpper && hasLower && hasDigit && hasSymbol)) {
      return "Password must include upper/lower case, a number, and a symbol.";
    }

    // Only SUPERUSER can create SUPERUSER
    if (form.role === "SUPERUSER" && !isSuperuser) {
      return "Only a platform superuser can create another superuser.";
    }

    return null;
  };

  const generateSecurePassword = () => {
    const upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
    const lower = "abcdefghijklmnopqrstuvwxyz";
    const digits = "0123456789";
    const symbols = "!@#$%^&*()-_=+[]{}<>?";
    const all = upper + lower + digits + symbols;

    const pick = (chars: string) =>
      chars[Math.floor(Math.random() * chars.length)];

    const base = [
      pick(upper),
      pick(lower),
      pick(digits),
      pick(symbols),
    ];

    for (let i = base.length; i < 14; i += 1) {
      base.push(pick(all));
    }

    const shuffled = base.sort(() => Math.random() - 0.5).join("");
    setForm((prev) => ({
      ...prev,
      password: shuffled,
      confirmPassword: shuffled,
    }));
  };

  const copyPassword = async () => {
    if (!form.password) return;
    try {
      if (!navigator.clipboard) {
        throw new Error("Clipboard unavailable");
      }
      await navigator.clipboard.writeText(form.password);
      setSuccess("Temporary password copied to clipboard.");
    } catch (err) {
      console.error("Failed to copy password", err);
      setError("Could not copy password. Please copy it manually.");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!currentUser) {
      setError("No user session found. Please sign in again.");
      return;
    }
    if (!isAdmin) {
      setError("You do not have permission to create users.");
      return;
    }

    const v = validate();
    if (v) {
      setError(v);
      return;
    }

    setSubmitting(true);
    try {
      const first = form.firstName.trim();
      const last = form.lastName.trim();

      const payload: AdminUserCreatePayload = {
        staff_code: form.staffCode.trim().toUpperCase(),
        email: form.email.trim().toLowerCase(),
        first_name: first,
        last_name: last,
        full_name: `${first} ${last}`.trim(),
        role: form.role,
        position_title: form.positionTitle.trim() || undefined,
        phone: form.phone.trim() || undefined,
        password: form.password,
        // NOTE:
        // Do NOT force amo_id here. adminUsers.ts resolves it safely:
        // - SUPERUSER: can target selected/active AMO
        // - others: forced to current user's AMO
      };

      await createAdminUser(payload);

      setSuccess("User created successfully.");
      setTimeout(() => navigate(backTarget), 600);
    } catch (err: any) {
      console.error("Failed to create user", err);

      const msg =
        err?.response?.data?.detail ||
        err?.detail ||
        err?.message ||
        "Failed to create user. Please try again.";
      setError(
        typeof msg === "string" ? msg : "Failed to create user. Please try again."
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (!currentUser) {
    return (
      <div className="page-root">
        <div className="card card--form">
          <h1>Create User</h1>
          <p>You are not signed in. Please sign in again.</p>
          <button className="btn btn-primary" onClick={() => navigate("/login")}>
            Go to login
          </button>
        </div>
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="page-root">
        <div className="card card--form">
          <h1>Access denied</h1>
          <p>
            You do not have permission to create users. Please contact the AMO
            Administrator or Quality/IT support.
          </p>
          <button className="btn btn-primary" onClick={() => navigate(backTarget)}>
            Back
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="page-root">
      <div className="page-header">
        <h1>{pageTitle}</h1>
        <p className="page-subtitle">
          Create a new AMO user. The target AMO is resolved from your session
          (and superuser support context if enabled).
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
              disabled={submitting}
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
              disabled={submitting}
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
              disabled={submitting}
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
              disabled={submitting}
            />
          </div>

          <div className="form-row">
            <label htmlFor="role">Role</label>
            <select
              id="role"
              name="role"
              value={form.role}
              onChange={handleChange}
              disabled={submitting}
            >
              {ROLE_OPTIONS.filter((r) => isSuperuser || r.value !== "SUPERUSER").map(
                (r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                )
              )}
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
              disabled={submitting}
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
              disabled={submitting}
            />
          </div>

          <div className="form-row">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              name="password"
              type={showPassword ? "text" : "password"}
              value={form.password}
              onChange={handleChange}
              required
              disabled={submitting}
            />
          </div>

          <div className="form-row">
            <label htmlFor="confirmPassword">Confirm Password</label>
            <input
              id="confirmPassword"
              name="confirmPassword"
              type={showPassword ? "text" : "password"}
              value={form.confirmPassword}
              onChange={handleChange}
              required
              disabled={submitting}
            />
          </div>

          <div className="form-row">
            <div className="form-actions form-actions--inline">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={generateSecurePassword}
                disabled={submitting}
              >
                Generate secure password
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setShowPassword((prev) => !prev)}
                disabled={submitting}
              >
                {showPassword ? "Hide password" : "Show password"}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={copyPassword}
                disabled={submitting || !form.password}
              >
                Copy password
              </button>
            </div>
            <p className="form-hint">
              Passwords must be at least 12 characters and include upper/lower
              case letters, a number, and a symbol.
            </p>
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => navigate(backTarget)}
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
