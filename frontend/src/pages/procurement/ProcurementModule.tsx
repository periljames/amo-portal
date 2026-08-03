import React, { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  Boxes,
  ClipboardCheck,
  FileSearch,
  HandCoins,
  Link2,
  PackageCheck,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  ShoppingCart,
  Truck,
  UsersRound,
  X,
} from "lucide-react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import PageHeader from "../../components/shared/PageHeader";
import {
  addSupplierApprovalScope,
  approveProcurementPurchaseOrder,
  createProcurementInvoiceMatch,
  createProcurementPurchaseOrder,
  createProcurementQualityHold,
  createProcurementQuote,
  createProcurementReceipt,
  createProcurementRequisition,
  createProcurementRfq,
  createProcurementSupplier,
  decideProcurementSupplier,
  evaluateProcurementQuote,
  getProcurementDashboard,
  getProcurementReferenceData,
  inspectProcurementReceipt,
  listProcurementPurchaseOrders,
  listProcurementQualityHolds,
  listProcurementQuotes,
  listProcurementReceipts,
  listProcurementRequisitions,
  listProcurementRfqs,
  listProcurementSuppliers,
  releaseProcurementQualityHold,
  releaseProcurementReceipt,
  sendProcurementPurchaseOrder,
  transitionProcurementRequisition,
} from "../../services/procurement";
import type {
  ProcurementDashboard,
  ProcurementPurchaseOrder,
  ProcurementReferenceData,
  ProcurementQualityHold,
  ProcurementQuote,
  ProcurementReceipt,
  ProcurementRequisition,
  ProcurementRFQ,
  ProcurementSupplier,
} from "../../types/procurement";
import "../../styles/procurement.css";

type Section = "home" | "requests" | "sourcing" | "orders" | "receiving" | "suppliers" | "control";
type ModalId = "request" | "supplier" | "scope" | "rfq" | "quote" | "po" | "receipt" | "hold" | "match" | null;

const NAV: Array<{ id: Section; label: string; icon: React.ComponentType<{ size?: number }> }> = [
  { id: "home", label: "Home", icon: ShoppingCart },
  { id: "requests", label: "Requests", icon: ClipboardCheck },
  { id: "sourcing", label: "Sourcing", icon: FileSearch },
  { id: "orders", label: "Orders", icon: HandCoins },
  { id: "receiving", label: "Receiving", icon: PackageCheck },
  { id: "suppliers", label: "Suppliers", icon: UsersRound },
  { id: "control", label: "Control", icon: ShieldCheck },
];

function decode(value: string | undefined): string {
  if (!value) return "";
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function sectionFromPath(pathname: string): Section {
  const parts = pathname.split("/").filter(Boolean);
  const moduleIndex = parts.findIndex((part) => part === "procurement" || part === "stores");
  const raw = moduleIndex >= 0 ? parts[moduleIndex + 1] : "";
  if (!raw || raw === "dashboard" || raw === "home") return "home";
  if (raw === "inventory" || raw === "goods-receipts") return "receiving";
  if (raw === "purchasing" || raw === "purchase-orders") return "orders";
  return NAV.some((item) => item.id === raw) ? (raw as Section) : "home";
}

function fmtDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

function money(value: string | number, currency = "USD"): string {
  const amount = Number(value || 0);
  return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(Number.isFinite(amount) ? amount : 0);
}

function tone(status: string): string {
  const normalized = status.toUpperCase();
  if (["APPROVED", "ACTIVE", "RELEASED", "MATCHED", "FULFILLED", "ACCEPTED"].some((item) => normalized.includes(item))) return "success";
  if (["AOG", "SUSPENDED", "REJECTED", "BLOCKED", "OVERDUE", "CRITICAL"].some((item) => normalized.includes(item))) return "danger";
  if (["PENDING", "QUARANTINED", "RESTRICTED", "VARIANCE", "REVIEW", "URGENT"].some((item) => normalized.includes(item))) return "warning";
  return "neutral";
}

function Status({ value }: { value: string }) {
  return <span className={`proc-status proc-status--${tone(value)}`}>{value.replaceAll("_", " ")}</span>;
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="proc-empty">{children}</div>;
}

function Field({
  label,
  name,
  value,
  onChange,
  type = "text",
  required,
  placeholder,
  children,
}: {
  label: string;
  name: string;
  value: string;
  onChange: (name: string, value: string) => void;
  type?: string;
  required?: boolean;
  placeholder?: string;
  children?: React.ReactNode;
}) {
  return (
    <label className="proc-field">
      <span>{label}{required ? " *" : ""}</span>
      {children || (
        <input
          name={name}
          value={value}
          onChange={(event) => onChange(name, event.target.value)}
          type={type}
          required={required}
          placeholder={placeholder}
        />
      )}
    </label>
  );
}

function Modal({
  title,
  subtitle,
  onClose,
  children,
}: {
  title: string;
  subtitle: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="proc-modal" role="dialog" aria-modal="true" aria-labelledby="proc-modal-title">
      <div className="proc-modal__backdrop" onClick={onClose} />
      <div className="proc-modal__panel">
        <header>
          <div>
            <h2 id="proc-modal-title">{title}</h2>
            <p>{subtitle}</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </header>
        {children}
      </div>
    </div>
  );
}

const ProcurementModule: React.FC = () => {
  const params = useParams<{ amoCode?: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const amoCode = decode(params.amoCode) || decode(location.pathname.split("/").filter(Boolean)[1]) || "UNKNOWN";
  const section = sectionFromPath(location.pathname);
  const basePath = `/maintenance/${encodeURIComponent(amoCode)}/procurement`;

  const [dashboard, setDashboard] = useState<ProcurementDashboard | null>(null);
  const [referenceData, setReferenceData] = useState<ProcurementReferenceData>({ locations: [], parts: [], vendors: [] });
  const [requisitions, setRequisitions] = useState<ProcurementRequisition[]>([]);
  const [rfqs, setRfqs] = useState<ProcurementRFQ[]>([]);
  const [quotes, setQuotes] = useState<ProcurementQuote[]>([]);
  const [orders, setOrders] = useState<ProcurementPurchaseOrder[]>([]);
  const [receipts, setReceipts] = useState<ProcurementReceipt[]>([]);
  const [suppliers, setSuppliers] = useState<ProcurementSupplier[]>([]);
  const [holds, setHolds] = useState<ProcurementQualityHold[]>([]);
  const [modal, setModal] = useState<ModalId>(null);
  const [selectedSupplierId, setSelectedSupplierId] = useState<number | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const setValue = (name: string, value: string) => setForm((current) => ({ ...current, [name]: value }));

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextDashboard, nextReferenceData, nextRequisitions, nextRfqs, nextQuotes, nextOrders, nextReceipts, nextSuppliers, nextHolds] =
        await Promise.all([
          getProcurementDashboard(amoCode),
          getProcurementReferenceData(amoCode),
          listProcurementRequisitions(amoCode),
          listProcurementRfqs(amoCode),
          listProcurementQuotes(amoCode),
          listProcurementPurchaseOrders(amoCode),
          listProcurementReceipts(amoCode),
          listProcurementSuppliers(amoCode),
          listProcurementQualityHolds(amoCode),
        ]);
      setDashboard(nextDashboard);
      setReferenceData(nextReferenceData);
      setRequisitions(nextRequisitions);
      setRfqs(nextRfqs);
      setQuotes(nextQuotes);
      setOrders(nextOrders);
      setReceipts(nextReceipts);
      setSuppliers(nextSuppliers);
      setHolds(nextHolds);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load Procurement.");
    } finally {
      setLoading(false);
    }
  }, [amoCode]);

  useEffect(() => { void load(); }, [load]);

  const filteredSuppliers = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return suppliers;
    return suppliers.filter((supplier) =>
      `${supplier.supplier_code} ${supplier.legal_name} ${supplier.supplier_type} ${supplier.status}`
        .toLowerCase()
        .includes(query),
    );
  }, [search, suppliers]);

  const open = (next: ModalId, defaults: Record<string, string> = {}) => {
    setForm(defaults);
    setNotice(null);
    setModal(next);
  };

  const finish = async (message: string) => {
    setModal(null);
    setForm({});
    setNotice(message);
    await load();
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!modal) return;
    setSaving(true);
    setError(null);
    try {
      if (modal === "request") {
        const selectedPart = referenceData.parts.find((part) => part.id === Number(form.inventoryPartId));
        await createProcurementRequisition(amoCode, {
          requisition_number: form.number,
          title: form.title,
          requesting_department: form.department,
          priority: form.priority || "ROUTINE",
          required_by: form.requiredBy || null,
          cost_centre: form.costCentre || null,
          justification: form.justification || null,
          source_module: form.sourceModule || null,
          source_record_id: form.sourceRecord || null,
          work_order_id: form.workOrderId ? Number(form.workOrderId) : null,
          aircraft_serial_number: form.aircraft || null,
          lines: [{
            inventory_part_id: selectedPart?.id || null,
            item_type: form.itemType || "PART",
            part_number: selectedPart?.part_number || form.partNumber || null,
            description: form.description || selectedPart?.description || selectedPart?.part_number || "Requested item",
            quantity: Number(form.quantity),
            uom: selectedPart?.uom || form.uom || "EA",
            criticality: form.criticality || "STANDARD",
            required_certification: form.certification || null,
            alternates_allowed: form.alternates === "yes",
            delivery_location_id: form.locationId ? Number(form.locationId) : null,
          }],
        });
        await finish("Requisition created in Draft.");
      } else if (modal === "supplier") {
        await createProcurementSupplier(amoCode, {
          supplier_code: form.code,
          legal_name: form.name,
          trading_name: form.tradingName || null,
          supplier_type: form.type || "DISTRIBUTOR",
          risk_level: form.risk || "MEDIUM",
          email: form.email || null,
          country: form.country || null,
          vendor_id: form.vendorId ? Number(form.vendorId) : null,
          qms_supplier_id: form.qmsSupplierId || null,
          default_currency: form.currency || "USD",
          quality_contact_name: form.qualityContact || null,
          quality_contact_email: form.qualityEmail || null,
        });
        await finish("Supplier created and sent to Quality review.");
      } else if (modal === "scope" && selectedSupplierId) {
        await addSupplierApprovalScope(amoCode, selectedSupplierId, {
          site_code: form.siteCode || "PRIMARY",
          category: form.category,
          product_family: form.productFamily || "ALL",
          manufacturer: form.manufacturer || null,
          authority: form.authority || "TENANT_QMS",
          approval_number: form.approvalNumber || null,
          effective_on: form.effectiveOn || null,
          expires_on: form.expiresOn || null,
          incoming_inspection_level: form.inspectionLevel || "STANDARD",
          restrictions: form.restrictions || null,
          evidence_reference: form.evidence || null,
          qms_evaluation_id: form.qmsEvaluationId || null,
          qms_audit_id: form.qmsAuditId || null,
        });
        await finish("Supplier approval scope recorded.");
      } else if (modal === "rfq") {
        await createProcurementRfq(amoCode, {
          rfq_number: form.number,
          requisition_id: Number(form.requisitionId),
          title: form.title,
          response_due_at: form.responseDue ? new Date(form.responseDue).toISOString() : null,
          terms: form.terms || null,
          quality_clauses: form.qualityClauses || null,
          supplier_ids: form.supplierIds.split(",").map((item) => Number(item.trim())).filter(Boolean),
          issue_immediately: true,
        });
        await finish("RFQ issued to selected suppliers.");
      } else if (modal === "quote") {
        await createProcurementQuote(amoCode, {
          rfq_id: Number(form.rfqId),
          supplier_id: Number(form.supplierId),
          quote_reference: form.reference,
          currency: form.currency || "USD",
          freight_amount: Number(form.freight || 0),
          tax_amount: Number(form.tax || 0),
          lead_time_days: form.leadTime ? Number(form.leadTime) : null,
          valid_until: form.validUntil || null,
          certification_offered: form.certification || null,
          technical_deviations: form.deviations || null,
          lines: [{
            requisition_line_id: form.requisitionLineId ? Number(form.requisitionLineId) : null,
            supplier_part_number: form.partNumber || null,
            manufacturer: form.manufacturer || null,
            quantity: Number(form.quantity),
            uom: form.uom || "EA",
            unit_price: Number(form.unitPrice),
            promised_date: form.promisedDate || null,
            traceability_statement: form.traceability || null,
            is_technically_compliant: form.compliant !== "no",
            deviation: form.lineDeviation || null,
          }],
        });
        await finish("Supplier quotation recorded.");
      } else if (modal === "po") {
        const selectedPart = referenceData.parts.find((part) => part.id === Number(form.inventoryPartId));
        await createProcurementPurchaseOrder(amoCode, {
          po_number: form.number,
          supplier_id: Number(form.supplierId),
          requisition_id: form.requisitionId ? Number(form.requisitionId) : null,
          quote_id: form.quoteId ? Number(form.quoteId) : null,
          priority: form.priority || "ROUTINE",
          currency: form.currency || "USD",
          freight_amount: Number(form.freight || 0),
          tax_amount: Number(form.tax || 0),
          delivery_terms: form.deliveryTerms || null,
          payment_terms: form.paymentTerms || null,
          quality_clauses: form.qualityClauses || null,
          ship_to_location_id: form.locationId ? Number(form.locationId) : null,
          promised_delivery_date: form.promisedDate || null,
          override_reference: form.overrideReference || null,
          override_reason: form.overrideReason || null,
          lines: [{
            inventory_part_id: selectedPart?.id || null,
            part_number: selectedPart?.part_number || form.partNumber || null,
            description: form.description || selectedPart?.description || selectedPart?.part_number || "Purchase item",
            manufacturer: form.manufacturer || null,
            quantity: Number(form.quantity),
            uom: selectedPart?.uom || form.uom || "EA",
            unit_price: Number(form.unitPrice),
            required_certification: form.certification || null,
            promised_date: form.promisedDate || null,
            work_order_id: form.workOrderId ? Number(form.workOrderId) : null,
            aircraft_serial_number: form.aircraft || null,
          }],
        });
        await finish("Purchase order created and routed for approval.");
      } else if (modal === "receipt") {
        const selectedOrder = orders.find((order) => order.id === Number(form.poId));
        const selectedLine = selectedOrder?.lines.find((line) => line.id === Number(form.poLineId));
        await createProcurementReceipt(amoCode, {
          receipt_number: form.number,
          purchase_order_id: Number(form.poId),
          delivery_note_number: form.deliveryNote || null,
          airway_bill_number: form.airwayBill || null,
          supplier_shipment_reference: form.shipmentReference || null,
          package_condition: form.packageCondition || null,
          quarantine_location_id: Number(form.quarantineLocationId),
          notes: form.notes || null,
          lines: [{
            purchase_order_line_id: Number(form.poLineId),
            inventory_part_id: selectedLine?.inventory_part_id || null,
            part_number: selectedLine?.part_number || form.partNumber,
            description: selectedLine?.description || null,
            quantity: Number(form.quantity),
            uom: selectedLine?.uom || "EA",
            lot_number: form.lotNumber || null,
            serial_number: form.serialNumber || null,
            expiry_date: form.expiryDate || null,
            release_document_type: form.releaseDocumentType || null,
            release_document_number: form.releaseDocumentNumber || null,
            release_document_issuer: form.releaseDocumentIssuer || null,
            release_document_date: form.releaseDocumentDate || null,
            chain_of_custody: form.chainOfCustody || null,
            target_location_id: Number(form.targetLocationId),
          }],
        });
        await finish("Receipt recorded in quarantine. No stock was released.");
      } else if (modal === "hold") {
        await createProcurementQualityHold(amoCode, {
          hold_number: form.number,
          target_type: form.targetType,
          target_id: form.targetId,
          reason: form.reason,
          qms_finding_id: form.qmsFindingId || null,
          qms_car_id: form.qmsCarId || null,
        });
        await finish("Quality hold placed.");
      } else if (modal === "match") {
        await createProcurementInvoiceMatch(amoCode, {
          purchase_order_id: Number(form.poId),
          invoice_reference: form.invoiceReference,
          invoice_total: Number(form.invoiceTotal),
          finance_reference: form.financeReference || null,
          tolerance_amount: Number(form.tolerance || 0.01),
          notes: form.notes || null,
        });
        await finish("Three-way match completed.");
      }
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "The action failed.");
    } finally {
      setSaving(false);
    }
  };

  const run = async (operation: () => Promise<unknown>, message: string) => {
    setSaving(true);
    setError(null);
    try {
      await operation();
      setNotice(message);
      await load();
    } catch (operationError) {
      setError(operationError instanceof Error ? operationError.message : "The action failed.");
    } finally {
      setSaving(false);
    }
  };

  const pageActions = (
    <div className="proc-header-actions">
      <button type="button" className="proc-btn proc-btn--secondary" onClick={() => void load()} disabled={loading}>
        <RefreshCw size={15} className={loading ? "is-spinning" : ""} /> Refresh
      </button>
      {section === "requests" && <button type="button" className="proc-btn proc-btn--primary" onClick={() => open("request")}><Plus size={15} /> New request</button>}
      {section === "sourcing" && <button type="button" className="proc-btn proc-btn--primary" onClick={() => open("rfq")}><Plus size={15} /> New RFQ</button>}
      {section === "orders" && <button type="button" className="proc-btn proc-btn--primary" onClick={() => open("po")}><Plus size={15} /> New PO</button>}
      {section === "receiving" && <button type="button" className="proc-btn proc-btn--primary" onClick={() => open("receipt")}><Plus size={15} /> Receive shipment</button>}
      {section === "suppliers" && <button type="button" className="proc-btn proc-btn--primary" onClick={() => open("supplier")}><Plus size={15} /> Add supplier</button>}
      {section === "control" && <button type="button" className="proc-btn proc-btn--primary" onClick={() => open("hold")}><Plus size={15} /> Place hold</button>}
    </div>
  );

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="stores">
      <div className="proc-page">
        <PageHeader
          compact
          eyebrow="Procurement & Supply Chain"
          title={NAV.find((item) => item.id === section)?.label || "Procurement"}
          subtitle="Controlled sourcing, supplier quality, purchase orders, receiving inspection, stock release, and financial matching."
          breadcrumbs={[{ label: "Procurement" }, { label: NAV.find((item) => item.id === section)?.label || "Home" }]}
          meta={<span className="proc-live"><span /> Tenant-scoped control</span>}
          actions={pageActions}
        />

        <nav className="proc-tabs" aria-label="Procurement work areas">
          {NAV.map((item) => {
            const Icon = item.icon;
            const target = item.id === "home" ? basePath : `${basePath}/${item.id}`;
            return (
              <button
                key={item.id}
                type="button"
                className={section === item.id ? "is-active" : ""}
                onClick={() => navigate(target)}
              >
                <Icon size={16} />
                {item.label}
              </button>
            );
          })}
        </nav>

        {error && <div className="proc-alert proc-alert--error"><AlertTriangle size={18} /><span>{error}</span><button type="button" onClick={() => setError(null)}>Dismiss</button></div>}
        {notice && <div className="proc-alert proc-alert--success"><BadgeCheck size={18} /><span>{notice}</span><button type="button" onClick={() => setNotice(null)}>Dismiss</button></div>}
        {loading && !dashboard ? <div className="proc-loading"><RefreshCw size={18} className="is-spinning" /> Loading Procurement control data…</div> : null}

        {section === "home" && dashboard && (
          <main className="proc-content">
            <section className="proc-kpis">
              {[
                ["Open requests", dashboard.counters.open_requisitions, "requests"],
                ["RFQs in market", dashboard.counters.rfqs_in_market, "sourcing"],
                ["Orders awaiting approval", dashboard.counters.orders_pending_approval, "orders"],
                ["Receipts in quarantine", dashboard.counters.quarantine_receipts, "receiving"],
                ["Active Quality holds", dashboard.counters.active_quality_holds, "control"],
                ["Approvals expiring", dashboard.counters.supplier_approvals_expiring, "suppliers"],
              ].map(([label, value, target]) => (
                <button key={String(label)} type="button" onClick={() => navigate(`${basePath}/${target}`)}>
                  <span>{label}</span><strong>{Number(value || 0)}</strong><ArrowRight size={15} />
                </button>
              ))}
            </section>

            <div className="proc-grid proc-grid--2">
              <section className="proc-panel">
                <header><div><span>My action queue</span><h2>Work requiring a decision</h2></div><ClipboardCheck size={20} /></header>
                {dashboard.action_queue.length ? dashboard.action_queue.map((item) => (
                  <button className="proc-list-row" key={`${item.kind}-${item.id}`} type="button" onClick={() => navigate(`${basePath}/${item.kind === "requisition" ? "requests" : "orders"}`)}>
                    <div><strong>{item.reference}</strong><span>{item.title}</span></div>
                    <div><Status value={item.status} /><small>{fmtDate(item.due_date)}</small></div>
                  </button>
                )) : <Empty>No approvals or sourcing decisions are waiting.</Empty>}
              </section>

              <section className="proc-panel">
                <header><div><span>Supply exceptions</span><h2>Late, blocked, or abnormal</h2></div><Truck size={20} /></header>
                {dashboard.supply_exceptions.length ? dashboard.supply_exceptions.map((item, index) => (
                  <div className="proc-list-row proc-list-row--static" key={index}>
                    <div><strong>{String(item.reference || "Exception")}</strong><span>{String(item.supplier || item.kind || "")}</span></div>
                    <small>{fmtDate(String(item.promised_delivery_date || ""))}</small>
                  </div>
                )) : <Empty>No current delivery exceptions.</Empty>}
              </section>

              <section className="proc-panel">
                <header><div><span>Quality control</span><h2>Quarantine and holds</h2></div><ShieldCheck size={20} /></header>
                {dashboard.quality_control.length ? dashboard.quality_control.map((item, index) => (
                  <div className="proc-list-row proc-list-row--static" key={index}>
                    <div><strong>{String(item.reference || item.target || "Quality item")}</strong><span>{String(item.kind || "")}</span></div>
                    <Status value={String(item.status || "OPEN")} />
                  </div>
                )) : <Empty>No quarantined receipts or active holds.</Empty>}
              </section>

              <section className="proc-panel">
                <header><div><span>Supplier health</span><h2>Approval and risk watch</h2></div><UsersRound size={20} /></header>
                {dashboard.supplier_health.length ? dashboard.supplier_health.map((item) => (
                  <button className="proc-list-row" key={Number(item.id)} type="button" onClick={() => navigate(`${basePath}/suppliers`)}>
                    <div><strong>{String(item.code)} · {String(item.name)}</strong><span>Risk: {String(item.risk_level)}</span></div>
                    <div><Status value={String(item.status)} /><small>{fmtDate(item.approval_expiry as string)}</small></div>
                  </button>
                )) : <Empty>No high-risk or restricted suppliers.</Empty>}
              </section>
            </div>

            <section className="proc-integration-strip">
              <div><Link2 size={18} /><span>Connected records</span></div>
              <strong>{Number(dashboard.integration_health.finance_vendor_links || 0)} Finance vendors</strong>
              <strong>{Number(dashboard.integration_health.qms_supplier_links || 0)} QMS suppliers</strong>
              <strong>{Number(dashboard.integration_health.maintenance_demand_links || 0)} maintenance/planning demands</strong>
              <strong>Inventory release: enforced</strong>
            </section>
          </main>
        )}

        {section === "requests" && (
          <main className="proc-content">
            <section className="proc-panel proc-panel--table">
              <header><div><span>Demand control</span><h2>Purchase requests</h2></div><Boxes size={20} /></header>
              {requisitions.length ? (
                <div className="proc-table-wrap"><table className="proc-table"><thead><tr><th>Request</th><th>Source</th><th>Required</th><th>Status</th><th>Actions</th></tr></thead><tbody>
                  {requisitions.map((row) => <tr key={row.id}>
                    <td><strong>{row.requisition_number}</strong><span>{row.title}</span><small>{row.lines.length} line(s) · {row.priority}</small></td>
                    <td>{row.requesting_department}<small>{row.source_module || "Manual"} {row.source_record_id || ""}</small></td>
                    <td>{fmtDate(row.required_by)}</td>
                    <td><Status value={row.status} /></td>
                    <td><div className="proc-row-actions">
                      {row.status === "DRAFT" && <button type="button" onClick={() => void run(() => transitionProcurementRequisition(amoCode, row.id, "SUBMIT"), "Request submitted.")}>Submit</button>}
                      {row.status === "SUBMITTED" && <button type="button" onClick={() => void run(() => transitionProcurementRequisition(amoCode, row.id, "TECHNICAL_APPROVE"), "Technical review recorded.")}>Technical approve</button>}
                      {row.status === "BUDGET_REVIEW" && <button type="button" onClick={() => void run(() => transitionProcurementRequisition(amoCode, row.id, "BUDGET_APPROVE"), "Budget review recorded.")}>Budget approve</button>}
                    </div></td>
                  </tr>)}
                </tbody></table></div>
              ) : <Empty>Create a request from Planning, Production, Maintenance, Stores, or another department.</Empty>}
            </section>
          </main>
        )}

        {section === "sourcing" && (
          <main className="proc-content">
            <div className="proc-grid proc-grid--2">
              <section className="proc-panel proc-panel--table">
                <header><div><span>Market engagement</span><h2>RFQs</h2></div><button type="button" onClick={() => open("rfq")}><Plus size={14} /> RFQ</button></header>
                {rfqs.length ? <div className="proc-table-wrap"><table className="proc-table"><thead><tr><th>RFQ</th><th>Response due</th><th>Status</th></tr></thead><tbody>
                  {rfqs.map((row) => <tr key={row.id}><td><strong>{row.rfq_number}</strong><span>{row.title}</span></td><td>{fmtDate(row.response_due_at)}</td><td><Status value={row.status} /></td></tr>)}
                </tbody></table></div> : <Empty>No RFQs issued.</Empty>}
              </section>
              <section className="proc-panel proc-panel--table">
                <header><div><span>Commercial evaluation</span><h2>Supplier quotations</h2></div><button type="button" onClick={() => open("quote")}><Plus size={14} /> Quote</button></header>
                {quotes.length ? <div className="proc-table-wrap"><table className="proc-table"><thead><tr><th>Quote</th><th>Value</th><th>Status</th><th /></tr></thead><tbody>
                  {quotes.map((row) => <tr key={row.id}><td><strong>{row.quote_reference}</strong><span>RFQ #{row.rfq_id} · Supplier #{row.supplier_id}</span></td><td>{money(row.total_amount, row.currency)}</td><td><Status value={row.status} /></td><td><button type="button" onClick={() => void run(() => evaluateProcurementQuote(amoCode, row.id, { status: "SHORTLISTED", evaluation_score: 80 }), "Quote shortlisted.")}>Shortlist</button></td></tr>)}
                </tbody></table></div> : <Empty>Record received quotations against an issued RFQ.</Empty>}
              </section>
            </div>
          </main>
        )}

        {section === "orders" && (
          <main className="proc-content">
            <section className="proc-panel proc-panel--table">
              <header><div><span>Commercial commitment</span><h2>Purchase orders</h2></div><HandCoins size={20} /></header>
              {orders.length ? <div className="proc-table-wrap"><table className="proc-table"><thead><tr><th>Order</th><th>Supplier</th><th>Value</th><th>Delivery</th><th>Status</th><th>Actions</th></tr></thead><tbody>
                {orders.map((row) => <tr key={row.id}>
                  <td><strong>{row.po_number}</strong><span>{row.lines.length} line(s) · {row.priority}</span></td>
                  <td>Supplier #{row.supplier_id}</td>
                  <td>{money(row.total_amount, row.currency)}</td>
                  <td>{fmtDate(row.promised_delivery_date)}</td>
                  <td><Status value={row.status} /></td>
                  <td><div className="proc-row-actions">
                    {row.status === "PENDING_TECHNICAL_REVIEW" && <button type="button" onClick={() => void run(() => approveProcurementPurchaseOrder(amoCode, row.id, "TECHNICAL"), "Technical PO approval recorded.")}>Technical</button>}
                    {row.status === "PENDING_BUDGET_APPROVAL" && <button type="button" onClick={() => void run(() => approveProcurementPurchaseOrder(amoCode, row.id, "BUDGET"), "Budget PO approval recorded.")}>Budget</button>}
                    {row.status === "PENDING_PROCUREMENT_APPROVAL" && <button type="button" onClick={() => void run(() => approveProcurementPurchaseOrder(amoCode, row.id, "PROCUREMENT"), "Procurement approval recorded.")}>Procurement</button>}
                    {row.status === "PENDING_QUALITY_APPROVAL" && <button type="button" onClick={() => void run(() => approveProcurementPurchaseOrder(amoCode, row.id, "QUALITY"), "Quality approval recorded.")}>Quality</button>}
                    {row.status === "APPROVED" && <button type="button" onClick={() => void run(() => sendProcurementPurchaseOrder(amoCode, row.id), "Purchase order sent.")}>Send</button>}
                  </div></td>
                </tr>)}
              </tbody></table></div> : <Empty>No controlled purchase orders.</Empty>}
            </section>
          </main>
        )}

        {section === "receiving" && (
          <main className="proc-content">
            <section className="proc-callout">
              <PackageCheck size={21} />
              <div><strong>External material enters quarantine.</strong><span>Receiving does not create serviceable stock. Independent inspection and Quality release are mandatory.</span></div>
            </section>
            <section className="proc-panel proc-panel--table">
              <header><div><span>Incoming material</span><h2>Receipts and inspection</h2></div><Truck size={20} /></header>
              {receipts.length ? <div className="proc-table-wrap"><table className="proc-table"><thead><tr><th>Receipt</th><th>PO</th><th>Trace</th><th>Status</th><th>Actions</th></tr></thead><tbody>
                {receipts.map((row) => <tr key={row.id}>
                  <td><strong>{row.receipt_number}</strong><span>{fmtDate(row.received_at)} · {row.lines.length} line(s)</span></td>
                  <td>PO #{row.purchase_order_id}</td>
                  <td>{row.delivery_note_number || "No delivery note"}<small>{row.airway_bill_number || ""}</small></td>
                  <td><Status value={row.status} /></td>
                  <td><div className="proc-row-actions">
                    {row.status === "QUARANTINED" && <button type="button" onClick={() => void run(() => inspectProcurementReceipt(amoCode, row.id, {
                      documentation_complete: true,
                      physical_condition_acceptable: true,
                      supplier_scope_valid: true,
                      part_identity_matches: true,
                      traceability_acceptable: true,
                      shelf_life_acceptable: true,
                      suspected_unapproved_part: false,
                      disposition: "ACCEPTED",
                      line_dispositions: Object.fromEntries(row.lines.map((line) => [line.id, "ACCEPTED"])),
                    }), "Receiving inspection completed.")}>Inspect</button>}
                    {row.status === "ACCEPTED_PENDING_RELEASE" && <button type="button" onClick={() => void run(() => releaseProcurementReceipt(amoCode, row.id, "Released after independent receiving inspection."), "Receipt released to serviceable inventory.")}>Quality release</button>}
                  </div></td>
                </tr>)}
              </tbody></table></div> : <Empty>No shipments have been received.</Empty>}
            </section>
          </main>
        )}

        {section === "suppliers" && (
          <main className="proc-content">
            <section className="proc-toolbar">
              <div className="proc-search"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search supplier, code, type, or status" /></div>
              <a href={`/maintenance/${encodeURIComponent(amoCode)}/quality/suppliers/approved-list`}><ShieldCheck size={15} /> Open QMS supplier control</a>
            </section>
            <section className="proc-supplier-grid">
              {filteredSuppliers.map((supplier) => (
                <article className="proc-supplier" key={supplier.id}>
                  <header><div><strong>{supplier.legal_name}</strong><span>{supplier.supplier_code} · {supplier.supplier_type}</span></div><Status value={supplier.status} /></header>
                  <dl>
                    <div><dt>Risk</dt><dd><Status value={supplier.risk_level} /></dd></div>
                    <div><dt>Finance</dt><dd>{supplier.vendor_id ? `Vendor #${supplier.vendor_id}` : "Not linked"}</dd></div>
                    <div><dt>QMS</dt><dd>{supplier.qms_supplier_id || "Pending link"}</dd></div>
                    <div><dt>Scopes</dt><dd>{supplier.approval_scopes.length}</dd></div>
                  </dl>
                  <div className="proc-supplier__scopes">
                    {supplier.approval_scopes.slice(0, 3).map((scope) => <span key={scope.id}>{scope.category} · {fmtDate(scope.expires_on)}</span>)}
                    {!supplier.approval_scopes.length && <span>No approved supply scope</span>}
                  </div>
                  <footer>
                    <button type="button" onClick={() => { setSelectedSupplierId(supplier.id); open("scope"); }}>Add scope</button>
                    {supplier.status === "UNDER_REVIEW" && <button type="button" onClick={() => void run(() => decideProcurementSupplier(amoCode, supplier.id, { action: "APPROVE" }), "Supplier approved.")}>Approve</button>}
                    {["APPROVED", "CONDITIONALLY_APPROVED"].includes(supplier.status) && <button type="button" className="is-danger" onClick={() => void run(() => decideProcurementSupplier(amoCode, supplier.id, { action: "SUSPEND", reason: "Suspended from Procurement control." }), "Supplier suspended.")}>Suspend</button>}
                  </footer>
                </article>
              ))}
              {!filteredSuppliers.length && <Empty>No suppliers match this view.</Empty>}
            </section>
          </main>
        )}

        {section === "control" && dashboard && (
          <main className="proc-content">
            <div className="proc-grid proc-grid--2">
              <section className="proc-panel">
                <header><div><span>Quality governance</span><h2>Active procurement holds</h2></div><button type="button" onClick={() => open("hold")}><Plus size={14} /> Hold</button></header>
                {holds.length ? holds.map((hold) => <div className="proc-list-row proc-list-row--static" key={hold.id}>
                  <div><strong>{hold.hold_number}</strong><span>{hold.target_type} #{hold.target_id} · {hold.reason}</span></div>
                  <div><Status value={hold.status} /><button type="button" onClick={() => void run(() => releaseProcurementQualityHold(amoCode, hold.id, "Released after Quality review."), "Quality hold released.")}>Release</button></div>
                </div>) : <Empty>No active Quality holds.</Empty>}
              </section>
              <section className="proc-panel">
                <header><div><span>Finance control</span><h2>Invoice matching</h2></div><button type="button" onClick={() => open("match")}><Plus size={14} /> Match invoice</button></header>
                <div className="proc-control-links">
                  <button type="button" onClick={() => open("match")}><HandCoins size={18} /><span><strong>Run three-way match</strong><small>PO value · Quality-released receipt · supplier invoice</small></span><ArrowRight size={16} /></button>
                  <button type="button" onClick={() => navigate(`${basePath}/suppliers`)}><Link2 size={18} /><span><strong>Review Finance vendor links</strong><small>Confirm every approved supplier has a vendor master</small></span><ArrowRight size={16} /></button>
                </div>
              </section>
              <section className="proc-panel">
                <header><div><span>Cross-module links</span><h2>Demand and execution</h2></div><Link2 size={20} /></header>
                <div className="proc-control-links">
                  <button type="button" onClick={() => navigate(`/maintenance/${amoCode}/planning`)}><ClipboardCheck size={18} /><span><strong>Planning</strong><small>Material demand and required-by dates</small></span><ArrowRight size={16} /></button>
                  <button type="button" onClick={() => navigate(`/maintenance/${amoCode}/production/dashboard`)}><Boxes size={18} /><span><strong>Production</strong><small>Work package material readiness</small></span><ArrowRight size={16} /></button>
                  <button type="button" onClick={() => navigate(`/maintenance/${amoCode}/maintenance/dashboard`)}><PackageCheck size={18} /><span><strong>Maintenance</strong><small>Work-order and task-card demand</small></span><ArrowRight size={16} /></button>
                </div>
              </section>
              <section className="proc-panel">
                <header><div><span>Control health</span><h2>Integration status</h2></div><BadgeCheck size={20} /></header>
                <dl className="proc-health">
                  {Object.entries(dashboard.integration_health).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{String(value)}</dd></div>)}
                </dl>
              </section>
            </div>
          </main>
        )}

        {modal && (
          <Modal title={{
            request: "New purchase request", supplier: "Add supplier", scope: "Supplier approval scope", rfq: "Issue RFQ",
            quote: "Record supplier quote", po: "Create purchase order", receipt: "Receive shipment", hold: "Place Quality hold", match: "Three-way invoice match",
          }[modal]} subtitle="Required controls are enforced by the backend workflow." onClose={() => setModal(null)}>
            <form className="proc-form" onSubmit={submit}>
              {modal === "request" && <>
                <Field label="Request number" name="number" value={form.number || ""} onChange={setValue} required placeholder="PR-2026-001" />
                <Field label="Title" name="title" value={form.title || ""} onChange={setValue} required />
                <Field label="Requesting department" name="department" value={form.department || ""} onChange={setValue} required />
                <Field label="Priority" name="priority" value={form.priority || "ROUTINE"} onChange={setValue}><select value={form.priority || "ROUTINE"} onChange={(e) => setValue("priority", e.target.value)}><option>ROUTINE</option><option>URGENT</option><option>AOG</option></select></Field>
                <Field label="Required by" name="requiredBy" value={form.requiredBy || ""} onChange={setValue} type="date" />
                <Field label="Source module" name="sourceModule" value={form.sourceModule || ""} onChange={setValue} placeholder="PLANNING / MAINTENANCE / PRODUCTION" />
                <Field label="Source record" name="sourceRecord" value={form.sourceRecord || ""} onChange={setValue} />
                <Field label="Work order ID" name="workOrderId" value={form.workOrderId || ""} onChange={setValue} type="number" />
                <Field label="Aircraft serial" name="aircraft" value={form.aircraft || ""} onChange={setValue} />
                <Field label="Part master" name="inventoryPartId" value={form.inventoryPartId || ""} onChange={setValue}><select value={form.inventoryPartId || ""} onChange={(e) => setValue("inventoryPartId", e.target.value)}><option value="">Ad-hoc item or service</option>{referenceData.parts.map((part) => <option key={part.id} value={part.id}>{part.part_number} · {part.description || "No description"}</option>)}</select></Field>
                <Field label="Part number" name="partNumber" value={form.partNumber || ""} onChange={setValue} />
                <Field label="Description" name="description" value={form.description || ""} onChange={setValue} required={!form.inventoryPartId} />
                <Field label="Quantity" name="quantity" value={form.quantity || "1"} onChange={setValue} type="number" required />
                <Field label="UOM" name="uom" value={form.uom || "EA"} onChange={setValue} required />
                <Field label="Criticality" name="criticality" value={form.criticality || "STANDARD"} onChange={setValue}><select value={form.criticality || "STANDARD"} onChange={(e) => setValue("criticality", e.target.value)}><option>STANDARD</option><option>CONTROLLED</option><option>CRITICAL</option></select></Field>
                <Field label="Required certification" name="certification" value={form.certification || ""} onChange={setValue} placeholder="EASA Form 1 / FAA 8130-3 / CoC" />
                <Field label="Delivery location" name="locationId" value={form.locationId || ""} onChange={setValue}><select value={form.locationId || ""} onChange={(e) => setValue("locationId", e.target.value)}><option value="">Select location</option>{referenceData.locations.map((location) => <option key={location.id} value={location.id}>{location.code} · {location.name}</option>)}</select></Field>
              </>}
              {modal === "supplier" && <>
                <Field label="Supplier code" name="code" value={form.code || ""} onChange={setValue} required />
                <Field label="Legal name" name="name" value={form.name || ""} onChange={setValue} required />
                <Field label="Trading name" name="tradingName" value={form.tradingName || ""} onChange={setValue} />
                <Field label="Supplier type" name="type" value={form.type || "DISTRIBUTOR"} onChange={setValue}><select value={form.type || "DISTRIBUTOR"} onChange={(e) => setValue("type", e.target.value)}><option>OEM</option><option>AUTHORIZED_DISTRIBUTOR</option><option>DISTRIBUTOR</option><option>BROKER</option><option>REPAIR_STATION</option><option>CALIBRATION_LAB</option><option>SUBCONTRACTOR</option><option>LOGISTICS</option></select></Field>
                <Field label="Risk level" name="risk" value={form.risk || "MEDIUM"} onChange={setValue}><select value={form.risk || "MEDIUM"} onChange={(e) => setValue("risk", e.target.value)}><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></Field>
                <Field label="Email" name="email" value={form.email || ""} onChange={setValue} type="email" />
                <Field label="Country" name="country" value={form.country || ""} onChange={setValue} />
                <Field label="Finance vendor" name="vendorId" value={form.vendorId || ""} onChange={setValue}><select value={form.vendorId || ""} onChange={(e) => setValue("vendorId", e.target.value)}><option value="">Create/link automatically</option>{referenceData.vendors.filter((vendor) => vendor.is_active).map((vendor) => <option key={vendor.id} value={vendor.id}>{vendor.code} · {vendor.name}</option>)}</select></Field>
                <Field label="QMS supplier ID" name="qmsSupplierId" value={form.qmsSupplierId || ""} onChange={setValue} />
                <Field label="Currency" name="currency" value={form.currency || "USD"} onChange={setValue} />
                <Field label="Quality contact" name="qualityContact" value={form.qualityContact || ""} onChange={setValue} />
                <Field label="Quality email" name="qualityEmail" value={form.qualityEmail || ""} onChange={setValue} type="email" />
              </>}
              {modal === "scope" && <>
                <Field label="Site code" name="siteCode" value={form.siteCode || "PRIMARY"} onChange={setValue} required />
                <Field label="Category" name="category" value={form.category || ""} onChange={setValue} required placeholder="PART / SERVICE / CALIBRATION" />
                <Field label="Product family" name="productFamily" value={form.productFamily || "ALL"} onChange={setValue} required />
                <Field label="Manufacturer" name="manufacturer" value={form.manufacturer || ""} onChange={setValue} />
                <Field label="Authority" name="authority" value={form.authority || "TENANT_QMS"} onChange={setValue} required />
                <Field label="Approval number" name="approvalNumber" value={form.approvalNumber || ""} onChange={setValue} />
                <Field label="Effective on" name="effectiveOn" value={form.effectiveOn || ""} onChange={setValue} type="date" />
                <Field label="Expires on" name="expiresOn" value={form.expiresOn || ""} onChange={setValue} type="date" />
                <Field label="Inspection level" name="inspectionLevel" value={form.inspectionLevel || "STANDARD"} onChange={setValue}><select value={form.inspectionLevel || "STANDARD"} onChange={(e) => setValue("inspectionLevel", e.target.value)}><option>STANDARD</option><option>ENHANCED</option><option>100_PERCENT</option></select></Field>
                <Field label="Evidence reference" name="evidence" value={form.evidence || ""} onChange={setValue} />
                <Field label="QMS evaluation ID" name="qmsEvaluationId" value={form.qmsEvaluationId || ""} onChange={setValue} />
                <Field label="QMS audit ID" name="qmsAuditId" value={form.qmsAuditId || ""} onChange={setValue} />
              </>}
              {modal === "rfq" && <>
                <Field label="RFQ number" name="number" value={form.number || ""} onChange={setValue} required />
                <Field label="Title" name="title" value={form.title || ""} onChange={setValue} required />
                <Field label="Requisition" name="requisitionId" value={form.requisitionId || ""} onChange={setValue}><select required value={form.requisitionId || ""} onChange={(e) => setValue("requisitionId", e.target.value)}><option value="">Select request</option>{requisitions.map((row) => <option key={row.id} value={row.id}>{row.requisition_number} · {row.title}</option>)}</select></Field>
                <Field label="Suppliers" name="supplierIds" value={form.supplierIds || ""} onChange={setValue}><select multiple required value={(form.supplierIds || "").split(",").filter(Boolean)} onChange={(e) => setValue("supplierIds", Array.from(e.currentTarget.selectedOptions, (option) => (option as HTMLOptionElement).value).join(","))}>{suppliers.filter((supplier) => ["APPROVED", "CONDITIONALLY_APPROVED"].includes(supplier.status)).map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.supplier_code} · {supplier.legal_name}</option>)}</select></Field>
                <Field label="Response due" name="responseDue" value={form.responseDue || ""} onChange={setValue} type="datetime-local" />
                <Field label="Terms" name="terms" value={form.terms || ""} onChange={setValue} />
                <Field label="Quality clauses" name="qualityClauses" value={form.qualityClauses || ""} onChange={setValue} />
              </>}
              {modal === "quote" && <>
                <Field label="RFQ" name="rfqId" value={form.rfqId || ""} onChange={setValue}><select required value={form.rfqId || ""} onChange={(e) => setValue("rfqId", e.target.value)}><option value="">Select RFQ</option>{rfqs.map((row) => <option key={row.id} value={row.id}>{row.rfq_number}</option>)}</select></Field>
                <Field label="Supplier" name="supplierId" value={form.supplierId || ""} onChange={setValue}><select required value={form.supplierId || ""} onChange={(e) => setValue("supplierId", e.target.value)}><option value="">Select supplier</option>{suppliers.map((row) => <option key={row.id} value={row.id}>{row.supplier_code} · {row.legal_name}</option>)}</select></Field>
                <Field label="Quote reference" name="reference" value={form.reference || ""} onChange={setValue} required />
                <Field label="Part number" name="partNumber" value={form.partNumber || ""} onChange={setValue} />
                <Field label="Manufacturer" name="manufacturer" value={form.manufacturer || ""} onChange={setValue} />
                <Field label="Quantity" name="quantity" value={form.quantity || "1"} onChange={setValue} type="number" required />
                <Field label="Unit price" name="unitPrice" value={form.unitPrice || ""} onChange={setValue} type="number" required />
                <Field label="Currency" name="currency" value={form.currency || "USD"} onChange={setValue} />
                <Field label="Lead time days" name="leadTime" value={form.leadTime || ""} onChange={setValue} type="number" />
                <Field label="Certification offered" name="certification" value={form.certification || ""} onChange={setValue} />
                <Field label="Traceability statement" name="traceability" value={form.traceability || ""} onChange={setValue} />
              </>}
              {modal === "po" && <>
                <Field label="PO number" name="number" value={form.number || ""} onChange={setValue} required />
                <Field label="Supplier" name="supplierId" value={form.supplierId || ""} onChange={setValue}><select required value={form.supplierId || ""} onChange={(e) => setValue("supplierId", e.target.value)}><option value="">Select supplier</option>{suppliers.map((row) => <option key={row.id} value={row.id}>{row.supplier_code} · {row.legal_name}</option>)}</select></Field>
                <Field label="Requisition" name="requisitionId" value={form.requisitionId || ""} onChange={setValue}><select value={form.requisitionId || ""} onChange={(e) => setValue("requisitionId", e.target.value)}><option value="">Optional</option>{requisitions.map((row) => <option key={row.id} value={row.id}>{row.requisition_number}</option>)}</select></Field>
                <Field label="Quote ID" name="quoteId" value={form.quoteId || ""} onChange={setValue} type="number" />
                <Field label="Priority" name="priority" value={form.priority || "ROUTINE"} onChange={setValue}><select value={form.priority || "ROUTINE"} onChange={(e) => setValue("priority", e.target.value)}><option>ROUTINE</option><option>URGENT</option><option>AOG</option></select></Field>
                <Field label="Part master" name="inventoryPartId" value={form.inventoryPartId || ""} onChange={setValue}><select value={form.inventoryPartId || ""} onChange={(e) => setValue("inventoryPartId", e.target.value)}><option value="">Ad-hoc service/item</option>{referenceData.parts.map((part) => <option key={part.id} value={part.id}>{part.part_number} · {part.description || "No description"}</option>)}</select></Field>
                <Field label="Part number" name="partNumber" value={form.partNumber || ""} onChange={setValue} />
                <Field label="Description" name="description" value={form.description || ""} onChange={setValue} required={!form.inventoryPartId} />
                <Field label="Manufacturer" name="manufacturer" value={form.manufacturer || ""} onChange={setValue} />
                <Field label="Quantity" name="quantity" value={form.quantity || "1"} onChange={setValue} type="number" required />
                <Field label="Unit price" name="unitPrice" value={form.unitPrice || ""} onChange={setValue} type="number" required />
                <Field label="Currency" name="currency" value={form.currency || "USD"} onChange={setValue} />
                <Field label="Required certification" name="certification" value={form.certification || ""} onChange={setValue} />
                <Field label="Promised date" name="promisedDate" value={form.promisedDate || ""} onChange={setValue} type="date" />
                <Field label="Quality clauses" name="qualityClauses" value={form.qualityClauses || ""} onChange={setValue} />
                <Field label="Ship-to location" name="locationId" value={form.locationId || ""} onChange={setValue}><select value={form.locationId || ""} onChange={(e) => setValue("locationId", e.target.value)}><option value="">Select location</option>{referenceData.locations.map((location) => <option key={location.id} value={location.id}>{location.code} · {location.name}</option>)}</select></Field>
              </>}
              {modal === "receipt" && <>
                <Field label="Receipt number" name="number" value={form.number || ""} onChange={setValue} required />
                <Field label="Purchase order" name="poId" value={form.poId || ""} onChange={setValue}><select required value={form.poId || ""} onChange={(e) => { setValue("poId", e.target.value); setValue("poLineId", ""); }}><option value="">Select PO</option>{orders.filter((row) => !["CLOSED", "CANCELLED"].includes(row.status)).map((row) => <option key={row.id} value={row.id}>{row.po_number}</option>)}</select></Field>
                <Field label="PO line" name="poLineId" value={form.poLineId || ""} onChange={setValue}><select required value={form.poLineId || ""} onChange={(e) => setValue("poLineId", e.target.value)}><option value="">Select line</option>{orders.find((row) => row.id === Number(form.poId))?.lines.map((line) => <option key={line.id} value={line.id}>{line.line_number} · {line.part_number || line.description}</option>)}</select></Field>
                <Field label="Quantity received" name="quantity" value={form.quantity || "1"} onChange={setValue} type="number" required />
                <Field label="Delivery note" name="deliveryNote" value={form.deliveryNote || ""} onChange={setValue} />
                <Field label="Airway bill" name="airwayBill" value={form.airwayBill || ""} onChange={setValue} />
                <Field label="Package condition" name="packageCondition" value={form.packageCondition || ""} onChange={setValue} />
                <Field label="Lot number" name="lotNumber" value={form.lotNumber || ""} onChange={setValue} />
                <Field label="Serial number" name="serialNumber" value={form.serialNumber || ""} onChange={setValue} />
                <Field label="Release document type" name="releaseDocumentType" value={form.releaseDocumentType || ""} onChange={setValue} />
                <Field label="Release document number" name="releaseDocumentNumber" value={form.releaseDocumentNumber || ""} onChange={setValue} />
                <Field label="Release document issuer" name="releaseDocumentIssuer" value={form.releaseDocumentIssuer || ""} onChange={setValue} />
                <Field label="Release document date" name="releaseDocumentDate" value={form.releaseDocumentDate || ""} onChange={setValue} type="date" />
                <Field label="Expiry date" name="expiryDate" value={form.expiryDate || ""} onChange={setValue} type="date" />
                <Field label="Chain of custody" name="chainOfCustody" value={form.chainOfCustody || ""} onChange={setValue} />
                <Field label="Quarantine location" name="quarantineLocationId" value={form.quarantineLocationId || ""} onChange={setValue}><select required value={form.quarantineLocationId || ""} onChange={(e) => setValue("quarantineLocationId", e.target.value)}><option value="">Select quarantine location</option>{referenceData.locations.map((location) => <option key={location.id} value={location.id}>{location.code} · {location.name}</option>)}</select></Field>
                <Field label="Target serviceable location" name="targetLocationId" value={form.targetLocationId || ""} onChange={setValue}><select required value={form.targetLocationId || ""} onChange={(e) => setValue("targetLocationId", e.target.value)}><option value="">Select serviceable location</option>{referenceData.locations.map((location) => <option key={location.id} value={location.id}>{location.code} · {location.name}</option>)}</select></Field>
              </>}
              {modal === "hold" && <>
                <Field label="Hold number" name="number" value={form.number || ""} onChange={setValue} required />
                <Field label="Target type" name="targetType" value={form.targetType || "SUPPLIER"} onChange={setValue}><select value={form.targetType || "SUPPLIER"} onChange={(e) => setValue("targetType", e.target.value)}><option>SUPPLIER</option><option>PURCHASE_ORDER</option><option>RECEIPT</option><option>PART</option><option>LOT</option><option>SERIAL</option><option>CERTIFICATE</option></select></Field>
                <Field label="Target ID" name="targetId" value={form.targetId || ""} onChange={setValue} required />
                <Field label="Reason" name="reason" value={form.reason || ""} onChange={setValue} required />
                <Field label="QMS finding ID" name="qmsFindingId" value={form.qmsFindingId || ""} onChange={setValue} />
                <Field label="QMS CAR ID" name="qmsCarId" value={form.qmsCarId || ""} onChange={setValue} />
              </>}
              {modal === "match" && <>
                <Field label="Purchase order" name="poId" value={form.poId || ""} onChange={setValue}><select required value={form.poId || ""} onChange={(e) => setValue("poId", e.target.value)}><option value="">Select PO</option>{orders.map((row) => <option key={row.id} value={row.id}>{row.po_number} · {money(row.total_amount, row.currency)}</option>)}</select></Field>
                <Field label="Supplier invoice reference" name="invoiceReference" value={form.invoiceReference || ""} onChange={setValue} required />
                <Field label="Invoice total" name="invoiceTotal" value={form.invoiceTotal || ""} onChange={setValue} type="number" required />
                <Field label="Finance reference" name="financeReference" value={form.financeReference || ""} onChange={setValue} />
                <Field label="Tolerance" name="tolerance" value={form.tolerance || "0.01"} onChange={setValue} type="number" />
              </>}
              <footer><button type="button" className="proc-btn proc-btn--secondary" onClick={() => setModal(null)}>Cancel</button><button type="submit" className="proc-btn proc-btn--primary" disabled={saving}>{saving ? "Saving…" : "Save and continue"}</button></footer>
            </form>
          </Modal>
        )}
      </div>
    </DepartmentLayout>
  );
};

export default ProcurementModule;
