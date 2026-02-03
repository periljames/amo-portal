import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { Button, InlineAlert, PageHeader, Panel } from "../components/UI/Admin";
import { getCachedUser } from "../services/auth";
import {
  fetchInvoiceDetail,
  fetchInvoiceDocument,
} from "../services/billing";
import type { InvoiceDetail } from "../types/billing";

type UrlParams = {
  amoCode?: string;
  invoiceId?: string;
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

const AdminInvoiceDetailPage: React.FC = () => {
  const { amoCode, invoiceId } = useParams<UrlParams>();
  const navigate = useNavigate();

  const currentUser = useMemo(() => getCachedUser(), []);
  const isTenantAdmin = !!currentUser?.is_superuser || !!currentUser?.is_amo_admin;

  const [invoice, setInvoice] = useState<InvoiceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
    const loadInvoice = async () => {
      if (!invoiceId) return;
      setLoading(true);
      setError(null);
      try {
        const data = await fetchInvoiceDetail(invoiceId);
        setInvoice(data as InvoiceDetail);
      } catch (err: any) {
        setError(err?.message || "Unable to load invoice.");
      } finally {
        setLoading(false);
      }
    };
    loadInvoice();
  }, [invoiceId]);

  if (currentUser && !isTenantAdmin) {
    return null;
  }

  return (
    <DepartmentLayout amoCode={amoCode ?? "UNKNOWN"} activeDepartment="admin-billing">
      <div className="admin-page">
        <PageHeader
          title="Invoice detail"
          subtitle={invoice ? invoice.description || "Invoice detail" : "Invoice detail"}
          actions={
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => navigate(`/maintenance/${amoCode}/admin/invoices`)}
            >
              Back to invoices
            </Button>
          }
        />

        {error && (
          <InlineAlert tone="danger" title="Error">
            <span>{error}</span>
          </InlineAlert>
        )}

        <div className="admin-page__grid">
          <Panel title="Invoice summary">
            {loading && <p>Loading invoice…</p>}
            {!loading && invoice && (
              <div className="form-grid">
                <div className="form-row">
                  <label>Status</label>
                  <input type="text" value={invoice.status} disabled />
                </div>
                <div className="form-row">
                  <label>Amount</label>
                  <input
                    type="text"
                    value={formatMoney(invoice.amount_cents, invoice.currency)}
                    disabled
                  />
                </div>
                <div className="form-row">
                  <label>Issued</label>
                  <input type="text" value={formatDateTime(invoice.issued_at)} disabled />
                </div>
                <div className="form-row">
                  <label>Due</label>
                  <input type="text" value={formatDateTime(invoice.due_at)} disabled />
                </div>
                <div className="form-row">
                  <label>Paid</label>
                  <input type="text" value={formatDateTime(invoice.paid_at)} disabled />
                </div>
              </div>
            )}
          </Panel>

          <Panel title="Status timeline">
            {!loading && invoice && (
              <ul style={{ margin: 0, paddingLeft: 16 }}>
                <li>Issued: {formatDateTime(invoice.issued_at)}</li>
                <li>Due: {formatDateTime(invoice.due_at)}</li>
                <li>Paid: {formatDateTime(invoice.paid_at)}</li>
              </ul>
            )}
          </Panel>

          <Panel title="Line items">
            {!loading && invoice?.ledger_entry && (
              <div className="card">
                <div className="card-header">
                  <div>
                    <strong>{invoice.ledger_entry.entry_type}</strong>
                    <p className="text-muted" style={{ margin: 0 }}>
                      {invoice.ledger_entry.description || "Ledger entry"}
                    </p>
                  </div>
                  <div>
                    {formatMoney(
                      invoice.ledger_entry.amount_cents,
                      invoice.ledger_entry.currency
                    )}
                  </div>
                </div>
              </div>
            )}
            {!loading && !invoice?.ledger_entry && (
              <p className="text-muted">No ledger entry available.</p>
            )}
          </Panel>

          <Panel title="Documents">
            {!loading && invoice && (
              <div className="form-actions">
                  <Button
                    type="button"
                    onClick={async () => {
                      const blob = await fetchInvoiceDocument(invoice.id, "html");
                      const url = URL.createObjectURL(blob);
                      const link = document.createElement("a");
                      link.href = url;
                      link.download = `invoice-${invoice.id}.html`;
                      link.click();
                      URL.revokeObjectURL(url);
                    }}
                  >
                    Download HTML
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={async () => {
                      const blob = await fetchInvoiceDocument(invoice.id, "pdf");
                      const url = URL.createObjectURL(blob);
                      const link = document.createElement("a");
                      link.href = url;
                      link.download = `invoice-${invoice.id}.pdf`;
                      link.click();
                      URL.revokeObjectURL(url);
                    }}
                  >
                    Download PDF
                  </Button>
              </div>
            )}
          </Panel>
        </div>
      </div>
    </DepartmentLayout>
  );
};

export default AdminInvoiceDetailPage;
