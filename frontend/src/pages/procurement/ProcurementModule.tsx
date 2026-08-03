import React, { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BadgeCheck,
  Boxes,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  ClipboardCheck,
  FileCheck2,
  FileText,
  HandCoins,
  LoaderCircle,
  PackageCheck,
  Paperclip,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  ShoppingCart,
  Truck,
  UsersRound,
  X,
} from "lucide-react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { useToast } from "../../components/feedback/ToastProvider";
import { getCachedUser } from "../../services/auth";
import {
  acknowledgeProcurementPurchaseOrder,
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
  ProcurementDocumentEntityType,
  ProcurementPurchaseOrder,
  ProcurementQualityHold,
  ProcurementQuote,
  ProcurementReceipt,
  ProcurementReferenceData,
  ProcurementRequisition,
  ProcurementRFQ,
  ProcurementSupplier,
} from "../../types/procurement";
import ProcurementDocumentCenter from "./ProcurementDocumentCenter";
import "../../styles/procurement.css";

type Section = "command" | "requests" | "sourcing" | "orders" | "receiving" | "suppliers" | "control" | "documents";
type Modal = "requisition" | "supplier" | "scope" | "rfq" | "quote" | "po" | "receipt" | "inspection" | "hold" | "match" | null;
type FormState = Record<string, string | boolean>;

type LoadState = {
  dashboard: ProcurementDashboard | null;
  referenceData: ProcurementReferenceData;
  requisitions: ProcurementRequisition[];
  rfqs: ProcurementRFQ[];
  quotes: ProcurementQuote[];
  orders: ProcurementPurchaseOrder[];
  receipts: ProcurementReceipt[];
  suppliers: ProcurementSupplier[];
  holds: ProcurementQualityHold[];
};

const EMPTY: LoadState = {
  dashboard: null,
  referenceData: { locations: [], parts: [], vendors: [] },
  requisitions: [],
  rfqs: [],
  quotes: [],
  orders: [],
  receipts: [],
  suppliers: [],
  holds: [],
};

const NAV: Array<{ id: Section; label: string; icon: React.ComponentType<{ size?: number }> }> = [
  { id: "command", label: "Command", icon: ClipboardCheck },
  { id: "requests", label: "Requests", icon: FileText },
  { id: "sourcing", label: "Sourcing", icon: HandCoins },
  { id: "orders", label: "Orders", icon: ShoppingCart },
  { id: "receiving", label: "Receiving", icon: Truck },
  { id: "suppliers", label: "Suppliers", icon: UsersRound },
  { id: "control", label: "Quality Control", icon: ShieldCheck },
  { id: "documents", label: "Documents", icon: Paperclip },
];

const ACTIVE_RECEIPT_STATUSES = new Set(["QUARANTINED", "DOCUMENT_REVIEW", "PHYSICAL_INSPECTION", "ACCEPTED_PENDING_RELEASE"]);
const QUALITY_ROLES = new Set(["QUALITY_MANAGER", "QUALITY_INSPECTOR", "AMO_ADMIN", "SUPERUSER"]);
const FINANCE_ROLES = new Set(["FINANCE_MANAGER", "ACCOUNTS_OFFICER", "AMO_ADMIN", "SUPERUSER"]);

function humanize(value?: string | null): string {
  return (value || "—").replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function money(value: string | number, currency = "USD"): string {
  const amount = Number(value || 0);
  return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 2 }).format(Number.isFinite(amount) ? amount : 0);
}

function dateLabel(value?: string | null): string {
  if (!value) return "Not set";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date);
}

function badgeClass(status?: string | null): string {
  const value = (status || "").toUpperCase();
  if (/REJECT|SUSPEND|EXPIRE|CANCEL|BLOCK|VOID/.test(value)) return "proc-badge--danger";
  if (/QUARANTINE|PENDING|REVIEW|HOLD|CONDITION|VARIANCE|AOG|URGENT/.test(value)) return "proc-badge--warning";
  if (/APPROVED|ACCEPTED|RELEASED|FULFILLED|MATCHED|CLOSED|ACTIVE/.test(value)) return "proc-badge--success";
  return "proc-badge--info";
}

function SectionEmpty({ icon: Icon, title, text, action }: { icon: React.ComponentType<{ size?: number }>; title: string; text: string; action?: React.ReactNode }) {
  return <div className="proc-empty-state"><Icon size={28} /><strong>{title}</strong><span>{text}</span>{action}</div>;
}

function Field({ label, required, wide, children }: { label: string; required?: boolean; wide?: boolean; children: React.ReactNode }) {
  return <label className={`proc-field${wide ? " proc-field--wide" : ""}`}><span>{label}{required ? " *" : ""}</span>{children}</label>;
}

function ModalShell({ title, subtitle, busy, onClose, onSubmit, children }: {
  title: string;
  subtitle: string;
  busy: boolean;
  onClose: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  children: React.ReactNode;
}) {
  return (
    <div className="proc-modal" role="dialog" aria-modal="true" aria-labelledby="proc-modal-title">
      <button type="button" className="proc-modal__backdrop" aria-label="Close dialog" onClick={onClose} />
      <div className="proc-modal__panel">
        <header><div><h2 id="proc-modal-title">{title}</h2><p>{subtitle}</p></div><button type="button" className="proc-icon-button" onClick={onClose} aria-label="Close"><X size={17} /></button></header>
        <form className="proc-form" onSubmit={onSubmit}>{children}<footer className="proc-form__footer"><button type="button" className="proc-button proc-button--ghost" onClick={onClose} disabled={busy}>Cancel</button><button type="submit" className="proc-button proc-button--primary" disabled={busy}>{busy ? <LoaderCircle className="is-spinning" size={16} /> : <BadgeCheck size={16} />}{busy ? "Saving controlled record" : "Save and continue"}</button></footer></form>
      </div>
    </div>
  );
}

export default function ProcurementModule() {
  const { amoCode = "" } = useParams<{ amoCode: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const { pushToast } = useToast();
  const user = getCachedUser();
  const role = user?.role || "";
  const canQuality = QUALITY_ROLES.has(role) || Boolean(user?.is_superuser);
  const canFinance = FINANCE_ROLES.has(role) || Boolean(user?.is_superuser);

  const pathSection = location.pathname.split("/").filter(Boolean)[3] as Section | undefined;
  const section: Section = NAV.some((item) => item.id === pathSection) ? pathSection! : "command";
  const [data, setData] = useState<LoadState>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [partialErrors, setPartialErrors] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [modal, setModal] = useState<Modal>(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<FormState>({});
  const [documentTarget, setDocumentTarget] = useState<{ type: ProcurementDocumentEntityType; id: string } | null>(null);

  const go = useCallback((next: Section) => navigate(`/maintenance/${encodeURIComponent(amoCode)}/procurement/${next}`), [amoCode, navigate]);

  const load = useCallback(async (announce = false) => {
    announce ? setRefreshing(true) : setLoading(true);
    const jobs = [
      ["dashboard", getProcurementDashboard(amoCode)],
      ["referenceData", getProcurementReferenceData(amoCode)],
      ["requisitions", listProcurementRequisitions(amoCode)],
      ["rfqs", listProcurementRfqs(amoCode)],
      ["quotes", listProcurementQuotes(amoCode)],
      ["orders", listProcurementPurchaseOrders(amoCode)],
      ["receipts", listProcurementReceipts(amoCode)],
      ["suppliers", listProcurementSuppliers(amoCode)],
      ["holds", listProcurementQualityHolds(amoCode)],
    ] as const;
    const results = await Promise.allSettled(jobs.map(([, promise]) => promise));
    const errors: string[] = [];
    setData((current) => {
      const next = { ...current } as LoadState;
      results.forEach((result, index) => {
        const key = jobs[index][0] as keyof LoadState;
        if (result.status === "fulfilled") (next as unknown as Record<string, unknown>)[key] = result.value;
        else errors.push(`${humanize(key)}: ${result.reason instanceof Error ? result.reason.message : "unavailable"}`);
      });
      return next;
    });
    setPartialErrors(errors);
    setLoading(false);
    setRefreshing(false);
    if (announce) pushToast({ title: errors.length ? "Procurement refreshed with warnings" : "Procurement refreshed", message: errors.length ? `${errors.length} data source${errors.length === 1 ? "" : "s"} could not be refreshed.` : "Operational data is current.", variant: errors.length ? "warning" : "success", sound: true });
  }, [amoCode, pushToast]);

  useEffect(() => { void load(); }, [load]);

  const openModal = (next: Exclude<Modal, null>, initial: FormState = {}) => { setForm(initial); setModal(next); };
  const closeModal = () => { if (!saving) { setModal(null); setForm({}); } };
  const setValue = (name: string, value: string | boolean) => setForm((current) => ({ ...current, [name]: value }));

  const activeHolds = data.holds.filter((hold) => hold.status === "ACTIVE");
  const quarantined = data.receipts.filter((receipt) => ACTIVE_RECEIPT_STATUSES.has(receipt.status));
  const aogRequests = data.requisitions.filter((request) => request.priority === "AOG" && !["CLOSED", "CANCELLED", "REJECTED"].includes(request.status));
  const restrictedSuppliers = data.suppliers.filter((supplier) => ["RESTRICTED", "SUSPENDED", "EXPIRED", "REJECTED"].includes(supplier.status));
  const countFor = (id: Section) => ({ requests: data.requisitions.length, sourcing: data.rfqs.length + data.quotes.length, orders: data.orders.length, receiving: quarantined.length, suppliers: data.suppliers.length, control: activeHolds.length, documents: 0, command: 0 }[id]);

  const filtered = useCallback(<T,>(items: T[], text: (item: T) => string) => {
    const value = query.trim().toLowerCase();
    return value ? items.filter((item) => text(item).toLowerCase().includes(value)) : items;
  }, [query]);

  const alertCards = [
    { show: activeHolds.length > 0, tone: "danger", icon: ShieldAlert, title: `${activeHolds.length} active Quality hold${activeHolds.length === 1 ? "" : "s"}`, text: "Supplier, order, receipt, release, or payment activity may be blocked.", target: "control" as Section },
    { show: aogRequests.length > 0, tone: "warning", icon: AlertTriangle, title: `${aogRequests.length} open AOG request${aogRequests.length === 1 ? "" : "s"}`, text: "Aircraft-on-ground demand requires immediate sourcing attention.", target: "requests" as Section },
    { show: quarantined.length > 0, tone: "warning", icon: Boxes, title: `${quarantined.length} receipt${quarantined.length === 1 ? "" : "s"} in quarantine`, text: "Material cannot enter serviceable stock until inspection and release are complete.", target: "receiving" as Section },
    { show: restrictedSuppliers.length > 0, tone: "danger", icon: UsersRound, title: `${restrictedSuppliers.length} restricted supplier${restrictedSuppliers.length === 1 ? "" : "s"}`, text: "Awards are blocked outside approved scope and active supplier status.", target: "suppliers" as Section },
  ].filter((alert) => alert.show);

  const act = async (label: string, operation: () => Promise<unknown>, success: string) => {
    setSaving(true);
    try {
      await operation();
      pushToast({ title: success, message: `${label} completed and the audit trail was updated.`, variant: "success", sound: true });
      await load();
    } catch (error) {
      pushToast({ title: `${label} failed`, message: error instanceof Error ? error.message : "The controlled action could not be completed.", variant: "error", sound: true, duration: 8000 });
    } finally { setSaving(false); }
  };

  const documentLink = (type: ProcurementDocumentEntityType, id: number) => { setDocumentTarget({ type, id: String(id) }); go("documents"); };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!modal) return;
    const number = (name: string) => Number(form[name] || 0);
    const text = (name: string) => String(form[name] || "").trim();
    const yes = (name: string) => form[name] === true || form[name] === "yes";
    const selectedIds = (name: string) => text(name).split(",").map((value) => Number(value.trim())).filter(Boolean);
    const chosenPart = data.referenceData.parts.find((part) => part.id === number("partId"));
    const chosenPo = data.orders.find((po) => po.id === number("poId"));
    const chosenPoLine = chosenPo?.lines.find((line) => line.id === number("poLineId"));

    const operations: Record<Exclude<Modal, null>, { label: string; success: string; run: () => Promise<unknown> }> = {
      requisition: { label: "Create requisition", success: "Requisition created", run: () => createProcurementRequisition(amoCode, {
        requisition_number: text("number"), title: text("title"), requesting_department: text("department"), priority: text("priority") || "ROUTINE", required_by: text("requiredBy") || null, justification: text("justification") || null, source_module: text("sourceModule") || null, source_record_id: text("sourceRecordId") || null, work_order_id: number("workOrderId") || null, aircraft_serial_number: text("aircraftSerial") || null,
        lines: [{ inventory_part_id: number("partId") || null, item_type: "PART", part_number: chosenPart?.part_number || text("partNumber") || null, description: text("description") || chosenPart?.description || chosenPart?.part_number, quantity: number("quantity"), uom: chosenPart?.uom || text("uom") || "EA", criticality: text("criticality") || "STANDARD", required_certification: text("certification") || null, delivery_location_id: number("locationId") || null }],
      }) },
      supplier: { label: "Create supplier", success: "Supplier registered", run: () => createProcurementSupplier(amoCode, { supplier_code: text("code"), legal_name: text("name"), trading_name: text("tradingName") || null, supplier_type: text("supplierType") || "DISTRIBUTOR", vendor_id: number("vendorId") || null, risk_level: text("risk") || "MEDIUM", email: text("email") || null, country: text("country") || null, default_currency: text("currency") || "USD", quality_contact_name: text("qualityContact") || null, quality_contact_email: text("qualityEmail") || null }) },
      scope: { label: "Add approval scope", success: "Supplier scope added", run: () => addSupplierApprovalScope(amoCode, number("supplierId"), { site_code: text("siteCode") || "PRIMARY", category: text("category"), product_family: text("productFamily") || "ALL", authority: text("authority") || "TENANT_QMS", approval_number: text("approvalNumber") || null, effective_on: text("effectiveOn") || null, expires_on: text("expiresOn") || null, restrictions: text("restrictions") || null, incoming_inspection_level: text("inspectionLevel") || "STANDARD", evidence_reference: text("evidenceReference") || null, qms_evaluation_id: text("qmsEvaluationId") || null, qms_audit_id: text("qmsAuditId") || null }) },
      rfq: { label: "Create RFQ", success: "RFQ issued", run: () => createProcurementRfq(amoCode, { rfq_number: text("number"), requisition_id: number("requisitionId"), title: text("title"), response_due_at: text("dueAt") || null, terms: text("terms") || null, quality_clauses: text("qualityClauses") || null, supplier_ids: selectedIds("supplierIds"), issue_immediately: yes("issueImmediately") }) },
      quote: { label: "Record quote", success: "Supplier quote recorded", run: () => createProcurementQuote(amoCode, { rfq_id: number("rfqId"), supplier_id: number("supplierId"), quote_reference: text("reference"), currency: text("currency") || "USD", freight_amount: number("freight"), tax_amount: number("tax"), lead_time_days: number("leadTime") || null, valid_until: text("validUntil") || null, certification_offered: text("certification") || null, technical_deviations: text("deviations") || null, lines: [{ quantity: number("quantity"), uom: text("uom") || "EA", unit_price: number("unitPrice"), manufacturer: text("manufacturer") || null, promised_date: text("promisedDate") || null, traceability_statement: text("traceability") || null, is_technically_compliant: !yes("nonCompliant"), deviation: text("deviations") || null }] }) },
      po: { label: "Create purchase order", success: "Purchase order prepared", run: () => createProcurementPurchaseOrder(amoCode, { po_number: text("number"), supplier_id: number("supplierId"), quote_id: number("quoteId") || null, requisition_id: number("requisitionId") || null, priority: text("priority") || "ROUTINE", currency: text("currency") || "USD", freight_amount: number("freight"), tax_amount: number("tax"), delivery_terms: text("deliveryTerms") || null, payment_terms: text("paymentTerms") || null, quality_clauses: text("qualityClauses") || null, ship_to_location_id: number("locationId") || null, promised_delivery_date: text("promisedDate") || null, lines: [{ inventory_part_id: number("partId") || null, part_number: chosenPart?.part_number || text("partNumber") || null, description: text("description") || chosenPart?.description || chosenPart?.part_number, quantity: number("quantity"), uom: chosenPart?.uom || text("uom") || "EA", unit_price: number("unitPrice"), manufacturer: text("manufacturer") || null, required_certification: text("certification") || null, promised_date: text("promisedDate") || null, work_order_id: number("workOrderId") || null, aircraft_serial_number: text("aircraftSerial") || null }] }) },
      receipt: { label: "Record receipt", success: "Receipt placed in quarantine", run: () => createProcurementReceipt(amoCode, { receipt_number: text("number"), purchase_order_id: number("poId"), delivery_note_number: text("deliveryNote") || null, airway_bill_number: text("airwayBill") || null, supplier_shipment_reference: text("shipmentReference") || null, package_condition: text("packageCondition") || null, quarantine_location_id: number("quarantineLocationId") || null, lines: [{ purchase_order_line_id: number("poLineId"), inventory_part_id: chosenPoLine?.inventory_part_id || null, part_number: chosenPoLine?.part_number || "UNSPECIFIED", description: chosenPoLine?.description || null, quantity: number("quantity"), uom: chosenPoLine?.uom || "EA", lot_number: text("lotNumber") || null, serial_number: text("serialNumber") || null, expiry_date: text("expiryDate") || null, release_document_type: text("releaseDocumentType") || null, release_document_number: text("releaseDocumentNumber") || null, release_document_issuer: text("releaseDocumentIssuer") || null, release_document_date: text("releaseDocumentDate") || null, chain_of_custody: text("chainOfCustody") || null, target_location_id: number("targetLocationId") }] }) },
      inspection: { label: "Complete inspection", success: "Receiving inspection recorded", run: () => inspectProcurementReceipt(amoCode, number("receiptId"), { documentation_complete: yes("documentationComplete"), physical_condition_acceptable: yes("physicalCondition"), supplier_scope_valid: yes("supplierScope"), part_identity_matches: yes("partIdentity"), traceability_acceptable: yes("traceabilityAcceptable"), shelf_life_acceptable: yes("shelfLife"), suspected_unapproved_part: yes("suspectedUnapprovedPart"), disposition: text("disposition") || "ACCEPTED", findings: text("findings") || null, conditions: text("conditions") || null, line_dispositions: {} }) },
      hold: { label: "Place Quality hold", success: "Quality hold placed", run: () => createProcurementQualityHold(amoCode, { hold_number: text("number"), target_type: text("targetType"), target_id: text("targetId"), reason: text("reason"), qms_finding_id: text("qmsFindingId") || null, qms_car_id: text("qmsCarId") || null }) },
      match: { label: "Perform invoice match", success: "Invoice matching completed", run: () => createProcurementInvoiceMatch(amoCode, { purchase_order_id: number("poId"), invoice_reference: text("invoiceReference"), invoice_total: number("invoiceTotal"), finance_reference: text("financeReference") || null, tolerance_amount: number("tolerance") || .01, notes: text("notes") || null }) },
    };
    const operation = operations[modal];
    setSaving(true);
    try {
      const created = await operation.run();
      pushToast({ title: operation.success, message: "The controlled record and audit event were saved.", variant: "success", sound: true });
      if (modal === "requisition" && created && typeof created === "object" && "id" in created) setDocumentTarget({ type: "REQUISITION", id: String((created as ProcurementRequisition).id) });
      setModal(null);
      setForm({});
      await load();
    } catch (error) {
      pushToast({ title: `${operation.label} failed`, message: error instanceof Error ? error.message : "The record could not be saved.", variant: "error", sound: true, duration: 8000 });
    } finally { setSaving(false); }
  };

  const searchBox = section !== "command" && section !== "documents" ? <label className="proc-search-box"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`Search ${NAV.find((item) => item.id === section)?.label.toLowerCase()}`} /></label> : null;

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="procurement">
      <div className="proc-page">
        <header className="proc-module-header"><div><span className="proc-eyebrow">Aviation supply chain control</span><h1>Procurement & Supply Chain</h1><p>Controlled demand, sourcing, purchasing, quarantine, Quality release, supplier approval, and retained evidence.</p></div><div className="proc-header-actions"><span className="proc-live"><span />Tenant controls active</span><span className="proc-sync">{data.dashboard?.as_of ? `Updated ${dateLabel(data.dashboard.as_of)}` : "Awaiting data"}</span><button type="button" className="proc-button proc-button--secondary" onClick={() => void load(true)} disabled={refreshing}>{refreshing ? <LoaderCircle className="is-spinning" size={16} /> : <RefreshCw size={16} />}Refresh</button><button type="button" className="proc-button proc-button--primary" onClick={() => openModal("requisition", { priority: "ROUTINE", quantity: "1", department: "MAINTENANCE" })}><Plus size={16} />New request</button></div></header>

        <nav className="proc-tabs" aria-label="Procurement work areas">{NAV.map(({ id, label, icon: Icon }) => <button key={id} type="button" className={section === id ? "is-active" : ""} onClick={() => go(id)} aria-current={section === id ? "page" : undefined}><Icon size={16} /><span>{label}</span>{countFor(id) ? <small>{countFor(id)}</small> : null}</button>)}</nav>

        {partialErrors.length ? <div className="proc-message proc-message--warning" role="alert"><AlertTriangle size={18} /><span>Some Procurement data could not be loaded. Available work remains usable: {partialErrors.join(" · ")}</span><button type="button" onClick={() => void load(true)}>Retry</button></div> : null}

        {alertCards.length ? <div className="proc-alert-ribbon" aria-label="Procurement warnings">{alertCards.map(({ tone, icon: Icon, title, text, target }) => <button type="button" key={title} className={`proc-alert-card proc-alert-card--${tone}`} onClick={() => go(target)}><Icon size={20} /><div><strong>{title}</strong><span>{text}</span></div><ChevronRight size={17} /></button>)}</div> : null}

        <main className="proc-content">
          {section === "command" ? <Command data={data} loading={loading} go={go} openModal={openModal} /> : null}
          {section === "requests" ? <Requests items={filtered(data.requisitions, (item) => `${item.requisition_number} ${item.title} ${item.requesting_department} ${item.status}`)} loading={loading} search={searchBox} openModal={openModal} documentLink={documentLink} act={act} /> : null}
          {section === "sourcing" ? <Sourcing rfqs={filtered(data.rfqs, (item) => `${item.rfq_number} ${item.title} ${item.status}`)} quotes={filtered(data.quotes, (item) => `${item.quote_reference} ${item.status}`)} loading={loading} search={searchBox} openModal={openModal} documentLink={documentLink} act={act} /> : null}
          {section === "orders" ? <Orders items={filtered(data.orders, (item) => `${item.po_number} ${item.status} ${item.supplier_id}`)} loading={loading} search={searchBox} openModal={openModal} documentLink={documentLink} act={act} /> : null}
          {section === "receiving" ? <Receiving items={filtered(data.receipts, (item) => `${item.receipt_number} ${item.status} ${item.delivery_note_number || ""}`)} loading={loading} search={searchBox} canQuality={canQuality} openModal={openModal} documentLink={documentLink} act={act} /> : null}
          {section === "suppliers" ? <Suppliers items={filtered(data.suppliers, (item) => `${item.supplier_code} ${item.legal_name} ${item.status} ${item.country || ""}`)} loading={loading} search={searchBox} openModal={openModal} documentLink={documentLink} act={act} /> : null}
          {section === "control" ? <Control holds={data.holds} orders={data.orders} receipts={quarantined} canQuality={canQuality} canFinance={canFinance} openModal={openModal} documentLink={documentLink} act={act} /> : null}
          {section === "documents" ? <ProcurementDocumentCenter amoCode={amoCode} records={{ requisitions: data.requisitions, rfqs: data.rfqs, quotes: data.quotes, orders: data.orders, receipts: data.receipts, suppliers: data.suppliers, holds: data.holds }} initialEntity={documentTarget} /> : null}
        </main>

        {modal ? <ModalShell title={humanize(modal)} subtitle="Required fields and backend controls are validated before the record is committed." busy={saving} onClose={closeModal} onSubmit={submit}>{renderFields(modal, form, setValue, data)}</ModalShell> : null}
      </div>
    </DepartmentLayout>
  );
}

function Heading({ eyebrow, title, text, action, search }: { eyebrow: string; title: string; text: string; action?: React.ReactNode; search?: React.ReactNode }) {
  return <header className="proc-section-heading proc-section-heading--split"><div><span className="proc-eyebrow">{eyebrow}</span><h2>{title}</h2><p>{text}</p></div><div className="proc-toolbar">{search}{action}</div></header>;
}

function Panel({ title, text, children, span }: { title: string; text: string; children: React.ReactNode; span?: boolean }) {
  return <section className={`proc-panel${span ? " proc-panel--span-2" : ""}`}><header><div><h2>{title}</h2><p>{text}</p></div></header>{children}</section>;
}

function LoadingList() { return <div className="proc-skeleton-list" role="status" aria-label="Loading Procurement data">{Array.from({ length: 4 }).map((_, index) => <span key={index} />)}</div>; }

function Command({ data, loading, go, openModal }: { data: LoadState; loading: boolean; go: (section: Section) => void; openModal: (modal: Exclude<Modal, null>, initial?: FormState) => void }) {
  const counters = data.dashboard?.counters || {};
  const kpis = [
    ["Open requests", counters.open_requisitions ?? data.requisitions.length, "requests", FileText],
    ["RFQs in market", counters.rfqs_in_market ?? data.rfqs.length, "sourcing", HandCoins],
    ["Orders for approval", counters.orders_pending_approval ?? data.orders.filter((item) => item.status.includes("PENDING")).length, "orders", ShoppingCart],
    ["Quarantine", counters.quarantine_receipts ?? data.receipts.filter((item) => ACTIVE_RECEIPT_STATUSES.has(item.status)).length, "receiving", Boxes],
    ["Quality holds", counters.active_quality_holds ?? data.holds.length, "control", ShieldAlert],
    ["Scopes expiring", counters.supplier_approvals_expiring ?? 0, "suppliers", UsersRound],
  ] as const;
  return <><div className="proc-kpi-grid">{kpis.map(([label, value, target, Icon]) => loading ? <span className="proc-kpi-skeleton" key={label} /> : <button type="button" key={label} className={`proc-kpi-card${Number(value) > 0 && ["Quality holds", "Quarantine", "Orders for approval"].includes(label) ? " is-attention" : ""}`} onClick={() => go(target)}><span>{label}</span><strong>{Number(value || 0)}</strong><Icon size={18} /></button>)}</div><div className="proc-command-grid"><Panel title="Action queue" text="Items requiring a Procurement, Quality, Finance, or technical decision.">{loading ? <LoadingList /> : data.dashboard?.action_queue?.length ? <div className="proc-worklist">{data.dashboard.action_queue.slice(0, 8).map((item) => <button type="button" className="proc-work-row" key={`${item.kind}-${item.id}`} onClick={() => go(item.kind.toLowerCase().includes("receipt") ? "receiving" : item.kind.toLowerCase().includes("supplier") ? "suppliers" : item.kind.toLowerCase().includes("requisition") ? "requests" : "orders")}><div><strong>{item.reference}</strong><span>{item.title}</span><small>{item.due_date ? `Due ${dateLabel(item.due_date)}` : "No due date"}</small></div><span className={`proc-badge ${badgeClass(item.status)}`}>{humanize(item.status)}</span><ChevronRight size={16} /></button>)}</div> : <SectionEmpty icon={CheckCircle2} title="Action queue is clear" text="No immediate controlled decision is waiting." />}</Panel><Panel title="Cross-department readiness" text="Operational links that keep purchasing traceable to the maintenance need."><div className="proc-integration-grid">{Object.entries(data.dashboard?.integration_health || {}).map(([key, value]) => <div key={key}><span>{humanize(key)}</span><strong className={Boolean(value) ? "is-positive" : ""}>{typeof value === "boolean" ? (value ? "Connected" : "Attention") : String(value ?? "—")}</strong></div>)}</div><div className="proc-document-prompt"><Paperclip size={19} /><span>Physical forms and external-system documents can be retained against requisitions, RFQs, quotes, orders, receipts, suppliers, and Quality holds.</span></div><button type="button" className="proc-panel-link" onClick={() => go("documents")}>Open linked document register <ChevronRight size={15} /></button></Panel><Panel title="Quick start" text="Start the correct controlled workflow without navigating through multiple screens." span><div className="proc-row-actions"><button type="button" onClick={() => openModal("requisition", { priority: "ROUTINE", quantity: "1", department: "MAINTENANCE" })}><Plus size={14} />New requisition</button><button type="button" onClick={() => openModal("supplier", { risk: "MEDIUM", supplierType: "DISTRIBUTOR", currency: "USD" })}><UsersRound size={14} />Register supplier</button><button type="button" onClick={() => openModal("rfq", { issueImmediately: true })}><HandCoins size={14} />Issue RFQ</button><button type="button" onClick={() => openModal("receipt", { quantity: "1" })}><Truck size={14} />Receive delivery</button></div></Panel></div></>;
}

function Requests({ items, loading, search, openModal, documentLink, act }: any) {
  return <><Heading eyebrow="Demand control" title="Parts and service requests" text="Trace every request to its department, aircraft, work order, required date, priority, and technical requirement." search={search} action={<button className="proc-button proc-button--primary" type="button" onClick={() => openModal("requisition", { priority: "ROUTINE", quantity: "1", department: "MAINTENANCE" })}><Plus size={16} />New requisition</button>} /><Panel title="Requisition register" text="Backend workflow states remain authoritative.">{loading ? <LoadingList /> : items.length ? <div className="proc-table-wrap"><table className="proc-table"><thead><tr><th>Request</th><th>Demand</th><th>Required</th><th>Status</th><th>Actions</th></tr></thead><tbody>{items.map((item: ProcurementRequisition) => <tr key={item.id}><td><strong>{item.requisition_number}</strong><span>{item.title}</span></td><td><strong>{item.requesting_department}</strong><span>{humanize(item.priority)} · {item.lines.length} line(s)</span></td><td>{dateLabel(item.required_by)}</td><td><span className={`proc-badge ${badgeClass(item.status)}`}>{humanize(item.status)}</span></td><td><div className="proc-row-actions"><button type="button" onClick={() => documentLink("REQUISITION", item.id)}><Paperclip size={13} />Documents</button>{item.status === "DRAFT" ? <button type="button" onClick={() => void act("Submit requisition", () => transitionProcurementRequisition(locationCode(), item.id, "SUBMIT"), "Requisition submitted")}>Submit</button> : null}{item.status === "SUBMITTED" ? <button type="button" onClick={() => void act("Technical approval", () => transitionProcurementRequisition(locationCode(), item.id, "TECHNICAL_APPROVE"), "Technical review completed")}>Technical approve</button> : null}{item.status === "TECHNICAL_REVIEW" ? <button type="button" onClick={() => void act("Budget approval", () => transitionProcurementRequisition(locationCode(), item.id, "BUDGET_APPROVE"), "Budget review completed")}>Budget approve</button> : null}{item.status === "BUDGET_REVIEW" ? <button type="button" onClick={() => void act("Send to sourcing", () => transitionProcurementRequisition(locationCode(), item.id, "SEND_TO_SOURCING"), "Request moved to sourcing")}>Source</button> : null}</div></td></tr>)}</tbody></table></div> : <SectionEmpty icon={FileText} title="No requisitions found" text="Create a controlled request or adjust the search." />}</Panel></>;
}

function Sourcing({ rfqs, quotes, loading, search, openModal, documentLink, act }: any) {
  return <><Heading eyebrow="Competitive sourcing" title="RFQs and supplier quotations" text="Invite approved suppliers, record quotations, assess technical compliance, and retain source evidence." search={search} action={<div className="proc-row-actions"><button type="button" onClick={() => openModal("rfq", { issueImmediately: true })}><Plus size={14} />New RFQ</button><button type="button" onClick={() => openModal("quote", { quantity: "1", currency: "USD" })}><Plus size={14} />Record quote</button></div>} /><div className="proc-grid proc-grid--2"><Panel title="RFQ register" text="Requests currently in market or evaluation.">{loading ? <LoadingList /> : rfqs.length ? <div className="proc-worklist">{rfqs.map((item: ProcurementRFQ) => <div className="proc-work-row proc-work-row--static" key={item.id}><div><strong>{item.rfq_number}</strong><span>{item.title}</span><small>{item.response_due_at ? `Due ${dateLabel(item.response_due_at)}` : "No response deadline"}</small></div><span className={`proc-badge ${badgeClass(item.status)}`}>{humanize(item.status)}</span><div className="proc-row-actions"><button type="button" onClick={() => documentLink("RFQ", item.id)}><Paperclip size={13} /></button></div></div>)}</div> : <SectionEmpty icon={HandCoins} title="No RFQs" text="Issue an RFQ from an approved requisition." />}</Panel><Panel title="Quotation register" text="Supplier offers and evaluation outcomes.">{loading ? <LoadingList /> : quotes.length ? <div className="proc-worklist">{quotes.map((item: ProcurementQuote) => <div className="proc-work-row proc-work-row--static" key={item.id}><div><strong>{item.quote_reference}</strong><span>{money(item.total_amount, item.currency)} · Supplier #{item.supplier_id}</span><small>{item.lead_time_days ? `${item.lead_time_days} day lead time` : "Lead time not recorded"}</small></div><span className={`proc-badge ${badgeClass(item.status)}`}>{humanize(item.status)}</span><div className="proc-row-actions"><button type="button" onClick={() => documentLink("QUOTE", item.id)}><Paperclip size={13} /></button>{item.status === "RECEIVED" ? <button type="button" onClick={() => void act("Evaluate quote", () => evaluateProcurementQuote(locationCode(), item.id, { status: "COMPLIANT", evaluation_score: 100, evaluation_notes: "Marked compliant from Procurement workspace." }), "Quote marked compliant")}>Compliant</button> : null}</div></div>)}</div> : <SectionEmpty icon={FileCheck2} title="No quotations" text="Record supplier quotations against an issued RFQ." />}</Panel></div></>;
}

function Orders({ items, loading, search, openModal, documentLink, act }: any) {
  const nextStage = (status: string) => ({ DRAFT: "TECHNICAL", PENDING_TECHNICAL_REVIEW: "TECHNICAL", PENDING_BUDGET_APPROVAL: "BUDGET", PENDING_PROCUREMENT_APPROVAL: "PROCUREMENT", PENDING_QUALITY_APPROVAL: "QUALITY" } as Record<string, string>)[status];
  return <><Heading eyebrow="Purchase control" title="Purchase orders" text="Supplier eligibility, staged approvals, segregation of duties, issue, acknowledgement, and delivery progress." search={search} action={<button type="button" className="proc-button proc-button--primary" onClick={() => openModal("po", { priority: "ROUTINE", quantity: "1", currency: "USD" })}><Plus size={16} />New order</button>} /><Panel title="Order register" text="Approval stages are enforced by role and backend state.">{loading ? <LoadingList /> : items.length ? <div className="proc-table-wrap"><table className="proc-table"><thead><tr><th>PO</th><th>Supplier</th><th>Value</th><th>Delivery</th><th>Status</th><th>Actions</th></tr></thead><tbody>{items.map((item: ProcurementPurchaseOrder) => <tr key={item.id}><td><strong>{item.po_number}</strong><span>{humanize(item.priority)} · {item.lines.length} line(s)</span></td><td>#{item.supplier_id}</td><td>{money(item.total_amount, item.currency)}</td><td>{dateLabel(item.promised_delivery_date)}</td><td><span className={`proc-badge ${badgeClass(item.status)}`}>{humanize(item.status)}</span></td><td><div className="proc-row-actions"><button type="button" onClick={() => documentLink("PURCHASE_ORDER", item.id)}><Paperclip size={13} />Documents</button>{nextStage(item.status) ? <button type="button" onClick={() => void act(`${humanize(nextStage(item.status))} approval`, () => approveProcurementPurchaseOrder(locationCode(), item.id, nextStage(item.status)!, "Approved from Procurement workspace."), "Purchase order approval recorded")}>Approve {humanize(nextStage(item.status))}</button> : null}{item.status === "APPROVED" ? <button type="button" onClick={() => void act("Send purchase order", () => sendProcurementPurchaseOrder(locationCode(), item.id), "Purchase order sent")}>Send</button> : null}{item.status === "SENT" ? <button type="button" onClick={() => void act("Acknowledge purchase order", () => acknowledgeProcurementPurchaseOrder(locationCode(), item.id, { supplier_ack_reference: `ACK-${item.po_number}` }), "Supplier acknowledgement recorded")}>Acknowledge</button> : null}</div></td></tr>)}</tbody></table></div> : <SectionEmpty icon={ShoppingCart} title="No purchase orders" text="Prepare an order only after supplier scope and sourcing checks." />}</Panel></>;
}

function Receiving({ items, loading, search, canQuality, openModal, documentLink, act }: any) {
  return <><Heading eyebrow="Incoming material" title="Receiving and quarantine" text="Every delivery enters quarantine until independent inspection and Quality release are complete." search={search} action={<button type="button" className="proc-button proc-button--primary" onClick={() => openModal("receipt", { quantity: "1" })}><Plus size={16} />Record receipt</button>} /><div className="proc-callout proc-callout--warning"><AlertTriangle size={18} /><div><strong>Quarantine is mandatory</strong><span>Receiving does not create serviceable stock. Only accepted lines move after backend Quality release and active-hold checks.</span></div></div><Panel title="Receipt register" text="Delivery, traceability, inspection, and release status.">{loading ? <LoadingList /> : items.length ? <div className="proc-table-wrap"><table className="proc-table"><thead><tr><th>Receipt</th><th>PO</th><th>Evidence</th><th>Received</th><th>Status</th><th>Actions</th></tr></thead><tbody>{items.map((item: ProcurementReceipt) => <tr key={item.id}><td><strong>{item.receipt_number}</strong><span>{item.lines.length} line(s)</span></td><td>#{item.purchase_order_id}</td><td>{item.delivery_note_number || "No delivery note"}</td><td>{dateLabel(item.received_at)}</td><td><span className={`proc-badge ${badgeClass(item.status)}`}>{humanize(item.status)}</span></td><td><div className="proc-row-actions"><button type="button" onClick={() => documentLink("RECEIPT", item.id)}><Paperclip size={13} />Documents</button>{canQuality && ACTIVE_RECEIPT_STATUSES.has(item.status) && item.status !== "ACCEPTED_PENDING_RELEASE" ? <button type="button" className="is-quality" onClick={() => openModal("inspection", { receiptId: String(item.id), documentationComplete: "yes", physicalCondition: "yes", supplierScope: "yes", partIdentity: "yes", traceabilityAcceptable: "yes", shelfLife: "yes", suspectedUnapprovedPart: "no", disposition: "ACCEPTED" })}><ClipboardCheck size={13} />Inspect</button> : null}{canQuality && item.status === "ACCEPTED_PENDING_RELEASE" ? <button type="button" className="is-quality" onClick={() => void act("Quality release", () => releaseProcurementReceipt(locationCode(), item.id, "Released after independent receiving inspection."), "Receipt released to inventory")}>Release</button> : null}</div></td></tr>)}</tbody></table></div> : <SectionEmpty icon={Truck} title="No receipts" text="Record a delivery against an issued purchase order." />}</Panel></>;
}

function Suppliers({ items, loading, search, openModal, documentLink, act }: any) {
  return <><Heading eyebrow="Approved supplier control" title="Supplier register" text="Finance vendor identity, Quality status, risk, approval scope, restrictions, and inspection level." search={search} action={<button type="button" className="proc-button proc-button--primary" onClick={() => openModal("supplier", { risk: "MEDIUM", supplierType: "DISTRIBUTOR", currency: "USD" })}><Plus size={16} />Register supplier</button>} />{loading ? <LoadingList /> : items.length ? <div className="proc-supplier-grid">{items.map((item: ProcurementSupplier) => <article className="proc-supplier-card" key={item.id}><header><div><strong>{item.legal_name}</strong><span>{item.supplier_code} · {item.country || "Country not set"}</span></div><span className={`proc-badge ${badgeClass(item.status)}`}>{humanize(item.status)}</span></header><div className="proc-supplier-card__health"><div><span>Risk</span><strong>{humanize(item.risk_level)}</strong></div><div><span>Finance vendor</span><strong>{item.vendor_id ? `#${item.vendor_id}` : "Not linked"}</strong></div></div><div className="proc-scope-list">{item.approval_scopes.length ? item.approval_scopes.map((scope) => <span key={scope.id}>{scope.category} · {humanize(scope.status)}</span>) : <span>No approved scope</span>}</div><footer><button type="button" onClick={() => documentLink("SUPPLIER", item.id)}><Paperclip size={13} />Documents</button><button type="button" className="is-quality" onClick={() => openModal("scope", { supplierId: String(item.id), siteCode: "PRIMARY", productFamily: "ALL", authority: "TENANT_QMS", inspectionLevel: "STANDARD" })}><ShieldCheck size={13} />Add scope</button>{["PROSPECTIVE", "UNDER_REVIEW", "CONDITIONALLY_APPROVED"].includes(item.status) ? <button type="button" onClick={() => void act("Approve supplier", () => decideProcurementSupplier(locationCode(), item.id, { action: "APPROVE", reason: "Approved from supplier control workspace." }), "Supplier approved")}>Approve</button> : null}{item.status === "APPROVED" ? <button type="button" className="is-danger" onClick={() => void act("Suspend supplier", () => decideProcurementSupplier(locationCode(), item.id, { action: "SUSPEND", reason: "Suspended from supplier control workspace." }), "Supplier suspended")}>Suspend</button> : null}</footer></article>)}</div> : <SectionEmpty icon={UsersRound} title="No suppliers" text="Register and link the Finance vendor, then Quality can approve scope." />}</>;
}

function Control({ holds, orders, receipts, canQuality, canFinance, openModal, documentLink, act }: any) {
  return <><Heading eyebrow="Independent oversight" title="Quality and Finance control" text="Quality holds, receiving release, supplier restrictions, QMS references, and invoice three-way matching." action={<div className="proc-row-actions">{canQuality ? <button type="button" className="is-quality" onClick={() => openModal("hold", { targetType: "RECEIPT" })}><ShieldAlert size={14} />Place hold</button> : null}{canFinance ? <button type="button" onClick={() => openModal("match", { tolerance: "0.01" })}><CircleDollarSign size={14} />Invoice match</button> : null}</div>} /><div className="proc-grid proc-grid--2"><Panel title="Active Quality holds" text="A hold blocks related supplier, PO, receipt, release, or Finance activity.">{holds.length ? <div className="proc-worklist">{holds.map((hold: ProcurementQualityHold) => <div className="proc-work-row proc-work-row--static" key={hold.id}><div><strong>{hold.hold_number}</strong><span>{hold.target_type} #{hold.target_id}</span><small>{hold.reason}</small></div><span className={`proc-badge ${badgeClass(hold.status)}`}>{humanize(hold.status)}</span><div className="proc-row-actions"><button type="button" onClick={() => documentLink("QUALITY_HOLD", hold.id)}><Paperclip size={13} /></button>{canQuality && hold.status === "ACTIVE" ? <button type="button" className="is-quality" onClick={() => void act("Release Quality hold", () => releaseProcurementQualityHold(locationCode(), hold.id, "Quality release recorded from control workspace."), "Quality hold released")}>Release</button> : null}</div></div>)}</div> : <SectionEmpty icon={CheckCircle2} title="No active Quality holds" text="No Procurement object is currently blocked by Quality." />}</Panel><Panel title="Release readiness" text="Receipts awaiting inspection or Quality release.">{receipts.length ? <div className="proc-worklist">{receipts.map((receipt: ProcurementReceipt) => <div className="proc-work-row proc-work-row--static" key={receipt.id}><div><strong>{receipt.receipt_number}</strong><span>PO #{receipt.purchase_order_id}</span><small>{receipt.delivery_note_number || "No delivery note linked"}</small></div><span className={`proc-badge ${badgeClass(receipt.status)}`}>{humanize(receipt.status)}</span><PackageCheck size={17} /></div>)}</div> : <SectionEmpty icon={PackageCheck} title="No release queue" text="No quarantined receipt is awaiting a Quality decision." />}</Panel><Panel title="Finance matching readiness" text="Orders available for invoice matching after released receipt value is known." span>{orders.length ? <div className="proc-table-wrap"><table className="proc-table"><thead><tr><th>PO</th><th>Status</th><th>Total</th><th>Received lines</th></tr></thead><tbody>{orders.map((order: ProcurementPurchaseOrder) => <tr key={order.id}><td><strong>{order.po_number}</strong></td><td><span className={`proc-badge ${badgeClass(order.status)}`}>{humanize(order.status)}</span></td><td>{money(order.total_amount, order.currency)}</td><td>{order.lines.filter((line) => Number(line.received_quantity) > 0).length}/{order.lines.length}</td></tr>)}</tbody></table></div> : <SectionEmpty icon={CircleDollarSign} title="No orders available" text="Create and approve a purchase order before matching invoices." />}</Panel></div></>;
}

function renderFields(modal: Exclude<Modal, null>, form: FormState, setValue: (name: string, value: string | boolean) => void, data: LoadState): React.ReactNode {
  const input = (name: string, type = "text", required = false) => <input type={type} required={required} value={String(form[name] || "")} onChange={(event) => setValue(name, event.target.value)} />;
  const textarea = (name: string, required = false) => <textarea rows={3} required={required} value={String(form[name] || "")} onChange={(event) => setValue(name, event.target.value)} />;
  const select = (name: string, options: Array<[string, string]>, required = false) => <select required={required} value={String(form[name] || "")} onChange={(event) => setValue(name, event.target.value)}><option value="">Select</option>{options.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>;
  const partOptions = data.referenceData.parts.map((part) => [String(part.id), `${part.part_number} · ${part.description || "No description"}`] as [string, string]);
  const locationOptions = data.referenceData.locations.map((location) => [String(location.id), `${location.code} · ${location.name}`] as [string, string]);
  const supplierOptions = data.suppliers.map((supplier) => [String(supplier.id), `${supplier.supplier_code} · ${supplier.legal_name}`] as [string, string]);
  const requisitionOptions = data.requisitions.map((request) => [String(request.id), `${request.requisition_number} · ${request.title}`] as [string, string]);
  const rfqOptions = data.rfqs.map((rfq) => [String(rfq.id), `${rfq.rfq_number} · ${rfq.title}`] as [string, string]);
  const quoteOptions = data.quotes.map((quote) => [String(quote.id), `${quote.quote_reference} · ${money(quote.total_amount, quote.currency)}`] as [string, string]);
  const poOptions = data.orders.map((po) => [String(po.id), `${po.po_number} · ${humanize(po.status)}`] as [string, string]);
  const vendorOptions = data.referenceData.vendors.map((vendor) => [String(vendor.id), `${vendor.code} · ${vendor.name}`] as [string, string]);
  const poLines = data.orders.find((po) => po.id === Number(form.poId))?.lines || [];

  if (modal === "requisition") return <><Field label="Requisition number" required>{input("number", "text", true)}</Field><Field label="Title" required>{input("title", "text", true)}</Field><Field label="Requesting department" required>{input("department", "text", true)}</Field><Field label="Priority" required>{select("priority", [["ROUTINE", "Routine"], ["URGENT", "Urgent"], ["AOG", "Aircraft on ground"]], true)}</Field><Field label="Required by">{input("requiredBy", "date")}</Field><Field label="Inventory part">{select("partId", partOptions)}</Field><Field label="Manual part number">{input("partNumber")}</Field><Field label="Description" required>{input("description", "text", true)}</Field><Field label="Quantity" required>{input("quantity", "number", true)}</Field><Field label="UOM">{input("uom")}</Field><Field label="Criticality">{select("criticality", [["STANDARD", "Standard"], ["CRITICAL", "Critical"], ["LIFE_LIMITED", "Life limited"]])}</Field><Field label="Required certification">{input("certification")}</Field><Field label="Delivery location">{select("locationId", locationOptions)}</Field><Field label="Source module">{input("sourceModule")}</Field><Field label="Source record ID">{input("sourceRecordId")}</Field><Field label="Work order ID">{input("workOrderId", "number")}</Field><Field label="Aircraft serial">{input("aircraftSerial")}</Field><Field label="Justification" wide>{textarea("justification")}</Field></>;
  if (modal === "supplier") return <><Field label="Supplier code" required>{input("code", "text", true)}</Field><Field label="Legal name" required>{input("name", "text", true)}</Field><Field label="Trading name">{input("tradingName")}</Field><Field label="Supplier type">{input("supplierType")}</Field><Field label="Finance vendor">{select("vendorId", vendorOptions)}</Field><Field label="Risk">{select("risk", [["LOW", "Low"], ["MEDIUM", "Medium"], ["HIGH", "High"], ["CRITICAL", "Critical"]])}</Field><Field label="Email">{input("email", "email")}</Field><Field label="Country">{input("country")}</Field><Field label="Currency">{input("currency")}</Field><Field label="Quality contact">{input("qualityContact")}</Field><Field label="Quality email">{input("qualityEmail", "email")}</Field></>;
  if (modal === "scope") return <><Field label="Supplier" required>{select("supplierId", supplierOptions, true)}</Field><Field label="Site code">{input("siteCode")}</Field><Field label="Category" required>{input("category", "text", true)}</Field><Field label="Product family">{input("productFamily")}</Field><Field label="Authority">{input("authority")}</Field><Field label="Approval number">{input("approvalNumber")}</Field><Field label="Effective date">{input("effectiveOn", "date")}</Field><Field label="Expiry date">{input("expiresOn", "date")}</Field><Field label="Inspection level">{input("inspectionLevel")}</Field><Field label="Evidence reference">{input("evidenceReference")}</Field><Field label="QMS evaluation ID">{input("qmsEvaluationId")}</Field><Field label="QMS audit ID">{input("qmsAuditId")}</Field><Field label="Restrictions" wide>{textarea("restrictions")}</Field></>;
  if (modal === "rfq") return <><Field label="RFQ number" required>{input("number", "text", true)}</Field><Field label="Requisition" required>{select("requisitionId", requisitionOptions, true)}</Field><Field label="Title" required wide>{input("title", "text", true)}</Field><Field label="Response deadline">{input("dueAt", "datetime-local")}</Field><Field label="Supplier IDs" required><input required value={String(form.supplierIds || "")} onChange={(event) => setValue("supplierIds", event.target.value)} placeholder="1, 2, 3" /></Field><Field label="Terms" wide>{textarea("terms")}</Field><Field label="Quality clauses" wide>{textarea("qualityClauses")}</Field><Field label="Issue immediately" wide><label className="proc-check"><input type="checkbox" checked={Boolean(form.issueImmediately)} onChange={(event) => setValue("issueImmediately", event.target.checked)} /><span>Issue RFQ after creation</span></label></Field></>;
  if (modal === "quote") return <><Field label="RFQ" required>{select("rfqId", rfqOptions, true)}</Field><Field label="Supplier" required>{select("supplierId", supplierOptions, true)}</Field><Field label="Quote reference" required>{input("reference", "text", true)}</Field><Field label="Currency">{input("currency")}</Field><Field label="Quantity" required>{input("quantity", "number", true)}</Field><Field label="UOM">{input("uom")}</Field><Field label="Unit price" required>{input("unitPrice", "number", true)}</Field><Field label="Freight">{input("freight", "number")}</Field><Field label="Tax">{input("tax", "number")}</Field><Field label="Lead time days">{input("leadTime", "number")}</Field><Field label="Valid until">{input("validUntil", "date")}</Field><Field label="Promised date">{input("promisedDate", "date")}</Field><Field label="Manufacturer">{input("manufacturer")}</Field><Field label="Certification">{input("certification")}</Field><Field label="Traceability" wide>{textarea("traceability")}</Field><Field label="Technical deviations" wide>{textarea("deviations")}</Field></>;
  if (modal === "po") return <><Field label="PO number" required>{input("number", "text", true)}</Field><Field label="Supplier" required>{select("supplierId", supplierOptions, true)}</Field><Field label="Quote">{select("quoteId", quoteOptions)}</Field><Field label="Requisition">{select("requisitionId", requisitionOptions)}</Field><Field label="Priority">{select("priority", [["ROUTINE", "Routine"], ["URGENT", "Urgent"], ["AOG", "AOG"]])}</Field><Field label="Currency">{input("currency")}</Field><Field label="Inventory part">{select("partId", partOptions)}</Field><Field label="Manual part number">{input("partNumber")}</Field><Field label="Description" required>{input("description", "text", true)}</Field><Field label="Quantity" required>{input("quantity", "number", true)}</Field><Field label="Unit price" required>{input("unitPrice", "number", true)}</Field><Field label="Freight">{input("freight", "number")}</Field><Field label="Tax">{input("tax", "number")}</Field><Field label="Manufacturer">{input("manufacturer")}</Field><Field label="Certification">{input("certification")}</Field><Field label="Ship-to location">{select("locationId", locationOptions)}</Field><Field label="Promised date">{input("promisedDate", "date")}</Field><Field label="Work order ID">{input("workOrderId", "number")}</Field><Field label="Aircraft serial">{input("aircraftSerial")}</Field><Field label="Delivery terms" wide>{textarea("deliveryTerms")}</Field><Field label="Payment terms" wide>{textarea("paymentTerms")}</Field><Field label="Quality clauses" wide>{textarea("qualityClauses")}</Field></>;
  if (modal === "receipt") return <><Field label="Receipt number" required>{input("number", "text", true)}</Field><Field label="Purchase order" required>{select("poId", poOptions, true)}</Field><Field label="PO line" required>{select("poLineId", poLines.map((line) => [String(line.id), `${line.part_number || "Item"} · ${line.description}`]), true)}</Field><Field label="Quantity" required>{input("quantity", "number", true)}</Field><Field label="Delivery note">{input("deliveryNote")}</Field><Field label="Airway bill">{input("airwayBill")}</Field><Field label="Shipment reference">{input("shipmentReference")}</Field><Field label="Package condition">{input("packageCondition")}</Field><Field label="Lot number">{input("lotNumber")}</Field><Field label="Serial number">{input("serialNumber")}</Field><Field label="Expiry date">{input("expiryDate", "date")}</Field><Field label="Release document type">{input("releaseDocumentType")}</Field><Field label="Release document number">{input("releaseDocumentNumber")}</Field><Field label="Release issuer">{input("releaseDocumentIssuer")}</Field><Field label="Release date">{input("releaseDocumentDate", "date")}</Field><Field label="Quarantine location">{select("quarantineLocationId", locationOptions)}</Field><Field label="Target serviceable location" required>{select("targetLocationId", locationOptions, true)}</Field><Field label="Chain of custody" wide>{textarea("chainOfCustody")}</Field></>;
  if (modal === "inspection") return <><Field label="Receipt ID" required>{input("receiptId", "number", true)}</Field>{[["documentationComplete", "Documentation complete"], ["physicalCondition", "Physical condition acceptable"], ["supplierScope", "Supplier scope valid"], ["partIdentity", "Part identity matches"], ["traceabilityAcceptable", "Traceability acceptable"], ["shelfLife", "Shelf life acceptable"]].map(([name, label]) => <Field label={label} key={name}>{select(name, [["yes", "Pass"], ["no", "Fail"]], true)}</Field>)}<Field label="Suspected unapproved part">{select("suspectedUnapprovedPart", [["no", "No"], ["yes", "Yes — escalate"]])}</Field><Field label="Disposition" required>{select("disposition", [["ACCEPTED", "Accepted"], ["CONDITIONALLY_ACCEPTED", "Conditionally accepted"], ["REJECTED", "Rejected"], ["RETURN_TO_SUPPLIER", "Return to supplier"], ["ESCALATED_TO_QUALITY", "Escalated to Quality"]], true)}</Field><Field label="Findings" wide>{textarea("findings")}</Field><Field label="Conditions" wide>{textarea("conditions")}</Field></>;
  if (modal === "hold") return <><Field label="Hold number" required>{input("number", "text", true)}</Field><Field label="Target type" required>{select("targetType", [["SUPPLIER", "Supplier"], ["PURCHASE_ORDER", "Purchase order"], ["RECEIPT", "Receipt"]], true)}</Field><Field label="Target ID" required>{input("targetId", "text", true)}</Field><Field label="QMS finding ID">{input("qmsFindingId")}</Field><Field label="QMS CAR ID">{input("qmsCarId")}</Field><Field label="Reason" required wide>{textarea("reason", true)}</Field></>;
  return <><Field label="Purchase order" required>{select("poId", poOptions, true)}</Field><Field label="Invoice reference" required>{input("invoiceReference", "text", true)}</Field><Field label="Invoice total" required>{input("invoiceTotal", "number", true)}</Field><Field label="Finance reference">{input("financeReference")}</Field><Field label="Tolerance">{input("tolerance", "number")}</Field><Field label="Notes" wide>{textarea("notes")}</Field></>;
}

function locationCode(): string {
  return window.location.pathname.split("/").filter(Boolean)[1] || "";
}
