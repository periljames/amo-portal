import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { Button, InlineAlert, PageHeader, Panel, Table } from "../components/UI/Admin";
import { getCachedUser } from "../services/auth";
import { fetchInvoices } from "../services/billing";
import {
  listAdminAmos,
  setAdminContext,
  setActiveAmoId,
  LS_ACTIVE_AMO_ID,
} from "../services/adminUsers";
import type { AdminAmoRead } from "../services/adminUsers";
import type { Invoice } from "../types/billing";

type UrlParams = {
  amoCode?: string;
};

const formatMoney = (amountCents: number, currency = "USD"): string => {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amountCents / 100);
};

const formatDateTime = (value?: string | null): string => {
  if (!value) return "—";
  const d = new Date(value);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

const AdminInvoicesPage: React.FC = () => {
  const { amoCode } = useParams<UrlParams>();
  const navigate = useNavigate();

  const currentUser = useMemo(() => getCachedUser(), []);
  const isTenantAdmin = !!currentUser?.is_superuser || !!currentUser?.is_amo_admin;

  const [amos, setAmos] = useState<AdminAmoRead[]>([]);
  const [activeAmoId, setActiveAmoIdState] = useState<string | null>(() => {
    const v = localStorage.getItem(LS_ACTIVE_AMO_ID);
    return v && v.trim() ? v.trim() : null;
  });
  const [loadingAmos, setLoadingAmos] = useState(false);
  const [amoError, setAmoError] = useState<string | null>(null);

  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const selectedAmo = useMemo(
    () => amos.find((a) => a.id === activeAmoId) || null,
    [amos, activeAmoId]
  );

  useEffect(() => {
    if (!currentUser) return;
    if (isTenantAdmin) return;

    if (amoCode) {
      navigate(`/maintenance/${amoCode}/admin/overview`, { replace: true });
      return;
    }
    navigate("/login", { replace: true });
  }, [amoCode, currentUser, isTenantAdmin, navigate]);

  useEffect(() => {
    if (!currentUser?.is_superuser) return;
    const loadAmos = async () => {
      setLoadingAmos(true);
      setAmoError(null);
      try {
        const data = await listAdminAmos();
        setAmos(data);
        if (!activeAmoId && data.length > 0) {
          setActiveAmoIdState(data[0].id);
          setActiveAmoId(data[0].id);
        }
      } catch (err: any) {
        setAmoError(err?.message || "Failed to load AMOs.");
      } finally {
        setLoadingAmos(false);
      }
    };
    loadAmos();
  }, [currentUser?.is_superuser, activeAmoId]);

  const syncAdminContext = async (amoId: string) => {
    if (!currentUser?.is_superuser) return;
    await setAdminContext({ active_amo_id: amoId });
  };

  const loadInvoices = async () => {
    setLoading(true);
    setError(null);
    try {
      if (selectedAmo) {
        await syncAdminContext(selectedAmo.id);
      }
      const data = await fetchInvoices();
      setInvoices(data);
    } catch (err: any) {
      setError(err?.message || "Unable to load invoices.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadInvoices();
  }, [selectedAmo?.id]);

  const handleAmoChange = async (nextAmoId: string) => {
    const v = (nextAmoId || "").trim();
    if (!v) return;
    setActiveAmoIdState(v);
    setActiveAmoId(v);
    await syncAdminContext(v);
  };

  const handlePrint = () => {
    window.print();
  };

  const handleDownloadInvoice = (invoice: Invoice) => {
    const payload = {
      ...invoice,
      amount_formatted: formatMoney(invoice.amount_cents, invoice.currency),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `invoice-${invoice.id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <DepartmentLayout amoCode={amoCode ?? "UNKNOWN"} activeDepartment="admin-billing">
      <div className="admin-page">
        <PageHeader
          title="Invoices"
          subtitle="Review invoices, download records, or print for your files."
          actions={
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => navigate(`/maintenance/${amoCode}/admin/billing`)}
            >
              Back to billing
            </Button>
          }
        />

        <div className="admin-page__grid">
          <Panel title="Invoice filters" subtitle="Pick the tenant and refresh the list.">
            {currentUser?.is_superuser && (
              <>
                {loadingAmos && <p>Loading AMOs…</p>}
                {amoError && (
                  <InlineAlert tone="danger" title="Error">
                    <span>{amoError}</span>
                  </InlineAlert>
                )}
                {!loadingAmos && !amoError && (
                  <div className="form-row">
                    <label htmlFor="amoSelect">Active AMO</label>
                    <select
                      id="amoSelect"
                      value={activeAmoId ?? ""}
                      onChange={(e) => handleAmoChange(e.target.value)}
                    >
                      {amos.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.amo_code} — {a.name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </>
            )}
            <div className="form-actions">
              <Button type="button" onClick={loadInvoices} disabled={loading}>
                {loading ? "Refreshing..." : "Refresh invoices"}
              </Button>
              <Button type="button" variant="secondary" onClick={handlePrint}>
                Print view
              </Button>
            </div>
          </Panel>

          <Panel title="Invoice list" subtitle={selectedAmo ? `${selectedAmo.amo_code} invoices` : "Invoices"}>
            {error && (
              <InlineAlert tone="danger" title="Error">
                <span>{error}</span>
              </InlineAlert>
            )}
            {loading && <p>Loading invoices…</p>}
            {!loading && invoices.length === 0 && (
              <p className="text-muted">No invoices available.</p>
            )}
            {!loading && invoices.length > 0 && (
              <Table>
                <thead>
                  <tr>
                    <th>Description</th>
                    <th>Status</th>
                    <th>Amount</th>
                    <th>Issued</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.map((invoice) => (
                    <tr key={invoice.id}>
                      <td>{invoice.description || "Invoice"}</td>
                      <td>{invoice.status}</td>
                      <td>{formatMoney(invoice.amount_cents, invoice.currency)}</td>
                      <td>{formatDateTime(invoice.issued_at)}</td>
                      <td>
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          onClick={() => handleDownloadInvoice(invoice)}
                        >
                          Download
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Panel>
        </div>
      </div>
    </DepartmentLayout>
  );
};

export default AdminInvoicesPage;
