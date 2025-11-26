// src/pages/AdminDashboardPage.tsx
import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getCachedUser } from "../services/auth";
import { listAdminUsers } from "../services/adminUsers";
import type { AdminUserRead } from "../services/adminUsers";

type UrlParams = {
  amoCode?: string;
};

const AdminDashboardPage: React.FC = () => {
  const { amoCode } = useParams<UrlParams>();
  const navigate = useNavigate();

  const [users, setUsers] = useState<AdminUserRead[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const currentUser = getCachedUser();

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        const data = await listAdminUsers();
        setUsers(data);
      } catch (err: any) {
        console.error("Failed to load users", err);
        setError(
          err?.message ||
            "Could not load users. Please try again or contact Quality/IT."
        );
      } finally {
        setLoading(false);
      }
    };

    load();
  }, []);

  const handleNewUser = () => {
    const target = amoCode
      ? `/maintenance/${amoCode}/admin/users/new`
      : "/login";
    navigate(target);
  };

  return (
    <DepartmentLayout amoCode={amoCode ?? "UNKNOWN"} activeDepartment="admin">
      <header className="page-header">
        <h1 className="page-header__title">User Administration</h1>
        <p className="page-header__subtitle">
          Manage AMO users, roles and access.
          {currentUser && (
            <>
              {" "}
              Signed in as <strong>{currentUser.full_name}</strong>.
            </>
          )}
        </p>
      </header>

      <section className="page-section">
        <div className="page-section__actions">
          <button
            type="button"
            className="primary-chip-btn"
            onClick={handleNewUser}
          >
            + Create user
          </button>
        </div>

        {loading && <p>Loading users…</p>}
        {error && <div className="alert alert-error">{error}</div>}

        {!loading && !error && (
          <div className="table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Staff code</th>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Department</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {users.length === 0 && (
                  <tr>
                    <td colSpan={6}>No users found for this AMO.</td>
                  </tr>
                )}
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>{u.staff_code}</td>
                    <td>{u.full_name}</td>
                    <td>{u.email}</td>
                    <td>{u.role}</td>
                    <td>{u.department_id ?? "—"}</td>
                    <td>{u.is_active ? "Active" : "Inactive"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </DepartmentLayout>
  );
};

export default AdminDashboardPage;
