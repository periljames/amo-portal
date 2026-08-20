import React, { useState } from "react";
import {
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  FileText,
  HandCoins,
  PackageCheck,
  Paperclip,
  Plus,
  ShieldAlert,
  ShieldCheck,
  ShoppingCart,
  Truck,
  UsersRound,
} from "lucide-react";

import {
  acknowledgeProcurementPurchaseOrder,
  sendProcurementPurchaseOrder,
  transitionProcurementRequisition,
} from "../../services/procurement";
import type {
  ProcurementDocumentEntityType,
  ProcurementPurchaseOrder,
  ProcurementQualityHold,
  ProcurementQuote,
  ProcurementReceipt,
  ProcurementRequisition,
  ProcurementRFQ,
  ProcurementSupplier,
} from "../../types/procurement";
import { Empty, RecordActions, Skeleton } from "./procurementUiShared";
import SupplierGovernancePanel from "./SupplierGovernancePanel";
import {
  badgeClass,
  dateLabel,
  humanize,
  money,
  type FormState,
  type Modal,
  type Section,
  type WorkspaceData,
} from "./procurementUiModel";

type OpenModal = (modal: Exclude<Modal, null>, initial?: FormState) => void;
type LinkDocument = (type: ProcurementDocumentEntityType, id: number) => void;
type ControlledAction = (label: string, operation: () => Promise<unknown>, success?: string) => Promise<void>;

function amoCode(): string {
  return window.location.pathname.split("/").filter(Boolean)[1] || "";
}

function Status({ value }: { value: string }) {
  return <span className={`proc-badge ${badgeClass(value)}`}>{humanize(value)}</span>;
}

export function Command({
  data,
  loading,
  go,
  openModal,
}: {
  data: WorkspaceData;
  loading: boolean;
  go: (section: Section) => void;
  openModal: OpenModal;
}) {
  if (loading && !data.dashboard) return <Skeleton rows={6} />;
  const counters = data.dashboard?.counters || {};
  const cards = [
    ["Open requests", counters.open_requisitions ?? data.requisitions.length, "requests" as Section, FileText],
    ["RFQs in market", counters.rfqs_in_market ?? data.rfqs.length, "sourcing" as Section, HandCoins],
    ["Orders awaiting approval", counters.orders_pending_approval ?? data.orders.filter((item) => item.status.includes("PENDING")).length, "orders" as Section, ShoppingCart],
    ["Receipts in quarantine", counters.quarantine_receipts ?? data.receipts.filter((item) => item.status !== "RELEASED").length, "receiving" as Section, PackageCheck],
    ["Active Quality holds", counters.active_quality_holds ?? data.holds.filter((item) => item.status === "ACTIVE").length, "control" as Section, ShieldAlert],
    ["Supplier approvals expiring", counters.supplier_approvals_expiring ?? 0, "suppliers" as Section, UsersRound],
  ] as const;

  return (
    <>
      <section className="proc-kpi-grid">
        {cards.map(([label, value, target, Icon]) => (
          <button type="button" key={label} className="proc-kpi" onClick={() => go(target)}>
            <Icon size={20} /><span>{label}</span><strong>{value}</strong><ChevronRight size={16} />
          </button>
        ))}
      </section>
      <section className="proc-command-grid">
        <div className="proc-panel">
          <header><div><h2>Action queue</h2><p>Highest-priority work requiring a controlled decision.</p></div></header>
          {data.dashboard?.action_queue?.length ? (
            <div className="proc-action-list">
              {data.dashboard.action_queue.slice(0, 8).map((item) => (
                <button key={`${item.kind}-${item.id}`} type="button" onClick={() => go(item.kind.includes("RECEIPT") ? "receiving" : item.kind.includes("ORDER") ? "orders" : "requests")}>
                  <Status value={item.status} /><div><strong>{item.reference}</strong><small>{item.title}</small></div><ChevronRight size={16} />
                </button>
              ))}
            </div>
          ) : <Empty icon={CheckCircle2} title="No queued exceptions" text="No controlled decisions are waiting in the current dashboard snapshot." />}
        </div>
        <div className="proc-panel">
          <header><div><h2>Fast capture</h2><p>Start a controlled record without leaving the command view.</p></div></header>
          <div className="proc-quick-grid">
            <button type="button" onClick={() => openModal("requisition", { priority: "ROUTINE", quantity: "1" })}><Plus size={18} /><span>Parts request</span></button>
            <button type="button" onClick={() => openModal("supplier", { risk: "MEDIUM", currency: "USD" })}><UsersRound size={18} /><span>Supplier</span></button>
            <button type="button" onClick={() => openModal("receipt", { quantity: "1" })}><Truck size={18} /><span>Receipt</span></button>
            <button type="button" onClick={() => openModal("hold")}><ShieldAlert size={18} /><span>Quality hold</span></button>
            <button type="button" onClick={() => go("documents")}><Paperclip size={18} /><span>Evidence</span></button>
          </div>
        </div>
      </section>
    </>
  );
}

export function Requests({
  items, loading, search, openModal, linkDocument, act,
}: {
  items: ProcurementRequisition[]; loading: boolean; search: React.ReactNode; openModal: OpenModal; linkDocument: LinkDocument; act: ControlledAction;
}) {
  return (
    <section className="proc-panel">
      <header className="proc-section-heading proc-section-heading--split"><div><h2>Demand requests</h2><p>Maintenance, Planning, and Production requirements with technical traceability.</p></div><div className="proc-toolbar">{search}<button type="button" className="proc-button proc-button--primary" onClick={() => openModal("requisition", { priority: "ROUTINE", quantity: "1" })}><Plus size={16} />New request</button></div></header>
      {loading ? <Skeleton /> : items.length ? (
        <div className="proc-table-wrap"><table className="proc-table"><thead><tr><th>Request</th><th>Department</th><th>Requirement</th><th>Status</th><th>Actions</th></tr></thead><tbody>
          {items.map((item) => <tr key={item.id}>
            <td><strong>{item.requisition_number}</strong><span>{item.title}</span></td>
            <td>{item.requesting_department}<small>{item.source_module ? `${item.source_module} · ${item.source_record_id || "linked"}` : "Portal request"}</small></td>
            <td>{item.lines[0]?.part_number || item.lines[0]?.description || "No line"}<small>{item.lines[0] ? `${item.lines[0].quantity} ${item.lines[0].uom} · ${humanize(item.priority)}` : ""}</small></td>
            <td><Status value={item.status} /><small>{dateLabel(item.required_by)}</small></td>
            <td><RecordActions><button type="button" onClick={() => linkDocument("REQUISITION", item.id)}><Paperclip size={14} />Evidence</button>{item.status === "DRAFT" ? <button type="button" onClick={() => void act("Submit requisition", () => transitionProcurementRequisition(amoCode(), item.id, "SUBMIT"))}>Submit</button> : null}{["SUBMITTED", "TECHNICAL_REVIEW"].includes(item.status) ? <button type="button" onClick={() => void act("Technical approval", () => transitionProcurementRequisition(amoCode(), item.id, "TECHNICAL_APPROVE"))}>Technical approve</button> : null}{item.status === "BUDGET_REVIEW" ? <button type="button" onClick={() => void act("Budget approval", () => transitionProcurementRequisition(amoCode(), item.id, "BUDGET_APPROVE"))}>Budget approve</button> : null}{item.status === "SOURCING" ? <button type="button" onClick={() => void act("Approve requisition", () => transitionProcurementRequisition(amoCode(), item.id, "APPROVE"))}>Approve</button> : null}</RecordActions></td>
          </tr>)}
        </tbody></table></div>
      ) : <Empty icon={FileText} title="No demand requests" text="Create the first traceable parts or service requirement." />}
    </section>
  );
}

export function Sourcing({ rfqs, quotes, loading, search, openModal, linkDocument }: {
  rfqs: ProcurementRFQ[]; quotes: ProcurementQuote[]; loading: boolean; search: React.ReactNode; openModal: OpenModal; linkDocument: LinkDocument;
}) {
  return (
    <div className="proc-stack">
      <section className="proc-panel">
        <header className="proc-section-heading proc-section-heading--split"><div><h2>RFQ register</h2><p>Controlled supplier invitations, deadlines, terms, and Quality clauses.</p></div><div className="proc-toolbar">{search}<button type="button" className="proc-button proc-button--primary" onClick={() => openModal("rfq", { issueImmediately: true })}><Plus size={16} />New RFQ</button></div></header>
        {loading ? <Skeleton /> : rfqs.length ? <div className="proc-card-list">{rfqs.map((item) => <article key={item.id}><div><strong>{item.rfq_number}</strong><span>{item.title}</span><small>Response due {dateLabel(item.response_due_at)}</small></div><Status value={item.status} /><RecordActions><button type="button" onClick={() => linkDocument("RFQ", item.id)}><Paperclip size={14} />Evidence</button></RecordActions></article>)}</div> : <Empty icon={HandCoins} title="No RFQs" text="Create an RFQ from an approved requisition." />}
      </section>
      <section className="proc-panel">
        <header className="proc-section-heading proc-section-heading--split"><div><h2>Supplier quotations</h2><p>Commercial, technical, traceability, and lead-time comparison.</p></div><button type="button" className="proc-button proc-button--secondary" onClick={() => openModal("quote", { quantity: "1", currency: "USD" })}><Plus size={16} />Record quote</button></header>
        {quotes.length ? <div className="proc-table-wrap"><table className="proc-table"><thead><tr><th>Quote</th><th>Supplier</th><th>Value</th><th>Status</th><th>Actions</th></tr></thead><tbody>{quotes.map((item) => <tr key={item.id}><td><strong>{item.quote_reference}</strong><span>RFQ #{item.rfq_id}</span></td><td>Supplier #{item.supplier_id}</td><td>{money(item.total_amount, item.currency)}<small>{item.lead_time_days ? `${item.lead_time_days} days` : "Lead time not set"}</small></td><td><Status value={item.status} /></td><td><RecordActions><button type="button" onClick={() => linkDocument("QUOTE", item.id)}><Paperclip size={14} />Evidence</button><button type="button" onClick={() => openModal("quoteEvaluation", { quoteId: String(item.id) })}>Evaluate</button></RecordActions></td></tr>)}</tbody></table></div> : <Empty icon={CircleDollarSign} title="No supplier quotations" text="Record quotations against issued RFQs." />}
      </section>
    </div>
  );
}

export function Orders({ items, loading, search, openModal, linkDocument, act }: {
  items: ProcurementPurchaseOrder[]; loading: boolean; search: React.ReactNode; openModal: OpenModal; linkDocument: LinkDocument; act: ControlledAction;
}) {
  return (
    <section className="proc-panel">
      <header className="proc-section-heading proc-section-heading--split"><div><h2>Purchase orders</h2><p>Supplier scope gates, staged approvals, delivery commitment, and spend control.</p></div><div className="proc-toolbar">{search}<button type="button" className="proc-button proc-button--primary" onClick={() => openModal("po", { priority: "ROUTINE", quantity: "1", currency: "USD" })}><Plus size={16} />New PO</button></div></header>
      {loading ? <Skeleton /> : items.length ? <div className="proc-table-wrap"><table className="proc-table"><thead><tr><th>Order</th><th>Supplier</th><th>Value</th><th>Delivery</th><th>Status</th><th>Actions</th></tr></thead><tbody>{items.map((item) => { const stage = item.status.includes("TECHNICAL") ? "TECHNICAL" : item.status.includes("BUDGET") ? "BUDGET" : item.status.includes("QUALITY") ? "QUALITY" : "PROCUREMENT"; return <tr key={item.id}><td><strong>{item.po_number}</strong><span>{item.lines.length} line{item.lines.length === 1 ? "" : "s"}</span></td><td>Supplier #{item.supplier_id}</td><td>{money(item.total_amount, item.currency)}</td><td>{dateLabel(item.promised_delivery_date)}<small>{item.supplier_ack_reference || "Awaiting acknowledgement"}</small></td><td><Status value={item.status} /></td><td><RecordActions><button type="button" onClick={() => linkDocument("PURCHASE_ORDER", item.id)}><Paperclip size={14} />Evidence</button>{item.status.includes("PENDING") ? <button type="button" onClick={() => openModal("poApproval", { poId: String(item.id), approvalStage: stage })}>Approve stage</button> : null}{item.status === "APPROVED" ? <button type="button" onClick={() => void act("Send purchase order", () => sendProcurementPurchaseOrder(amoCode(), item.id))}>Send</button> : null}{item.status === "SENT" ? <button type="button" onClick={() => void act("Acknowledge purchase order", () => acknowledgeProcurementPurchaseOrder(amoCode(), item.id, { supplier_ack_reference: `ACK-${item.po_number}`, acknowledged_at: new Date().toISOString() }))}>Acknowledge</button> : null}</RecordActions></td></tr>; })}</tbody></table></div> : <Empty icon={ShoppingCart} title="No purchase orders" text="Prepare a purchase order from a selected quotation or requisition." />}
    </section>
  );
}

export function Receiving({ items, loading, search, canQuality, openModal, linkDocument }: {
  items: ProcurementReceipt[]; loading: boolean; search: React.ReactNode; canQuality: boolean; openModal: OpenModal; linkDocument: LinkDocument;
}) {
  return (
    <section className="proc-panel">
      <header className="proc-section-heading proc-section-heading--split"><div><h2>Receiving and quarantine</h2><p>Every delivery remains quarantined until independent inspection and Quality release.</p></div><div className="proc-toolbar">{search}<button type="button" className="proc-button proc-button--primary" onClick={() => openModal("receipt", { quantity: "1" })}><Plus size={16} />Record receipt</button></div></header>
      {loading ? <Skeleton /> : items.length ? <div className="proc-table-wrap"><table className="proc-table"><thead><tr><th>Receipt</th><th>PO</th><th>Delivery evidence</th><th>Status</th><th>Actions</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><strong>{item.receipt_number}</strong><span>{item.lines.length} received line{item.lines.length === 1 ? "" : "s"}</span></td><td>PO #{item.purchase_order_id}</td><td>{item.delivery_note_number || "No delivery note"}<small>{item.airway_bill_number || "No airway bill"}</small></td><td><Status value={item.status} /><small>{dateLabel(item.received_at)}</small></td><td><RecordActions><button type="button" onClick={() => linkDocument("RECEIPT", item.id)}><Paperclip size={14} />Evidence</button>{canQuality && ["QUARANTINED", "DOCUMENT_REVIEW", "PHYSICAL_INSPECTION"].includes(item.status) ? <button type="button" onClick={() => openModal("inspection", { receiptId: String(item.id) })}>Inspect</button> : null}{canQuality && item.status === "ACCEPTED_PENDING_RELEASE" ? <button type="button" onClick={() => openModal("receiptRelease", { receiptId: String(item.id) })}>Release</button> : null}</RecordActions></td></tr>)}</tbody></table></div> : <Empty icon={Truck} title="No receipts" text="Record an incoming delivery against a controlled purchase order." />}
    </section>
  );
}

export function Suppliers({
  items, loading, search, openModal, linkDocument, canQuality, currentUserId, onChanged,
}: {
  items: ProcurementSupplier[];
  loading: boolean;
  search: React.ReactNode;
  openModal: OpenModal;
  linkDocument: LinkDocument;
  canQuality: boolean;
  currentUserId?: string | null;
  onChanged: () => Promise<void>;
}) {
  const [governedSupplierId, setGovernedSupplierId] = useState<number | null>(null);
  const governedSupplier = items.find((item) => item.id === governedSupplierId) || null;
  return (
    <section className="proc-panel">
      <header className="proc-section-heading proc-section-heading--split"><div><h2>Approved supplier control</h2><p>Evaluation evidence, independent review, approved scope, validity, surveillance and lifecycle decisions.</p></div><div className="proc-toolbar">{search}<button type="button" className="proc-button proc-button--primary" onClick={() => openModal("supplier", { risk: "MEDIUM", currency: "USD" })}><Plus size={16} />Supplier</button></div></header>
      {loading ? <Skeleton /> : items.length ? <div className="proc-card-list proc-card-list--suppliers">{items.map((item) => <article key={item.id}><div className="proc-supplier-head"><div><strong>{item.supplier_code}</strong><span>{item.legal_name}</span></div><Status value={item.status} /></div><div className="proc-supplier-meta"><span>{humanize(item.supplier_type)}</span><span>{humanize(item.risk_level)} risk</span><span>{item.country || "Country not set"}</span><span>{item.approval_scopes.length} governed scope{item.approval_scopes.length === 1 ? "" : "s"}</span></div><RecordActions><button type="button" onClick={() => linkDocument("SUPPLIER", item.id)}><Paperclip size={14} />Evidence</button><button type="button" onClick={() => setGovernedSupplierId(item.id)}><ShieldCheck size={14} />Governance</button></RecordActions></article>)}</div> : <Empty icon={UsersRound} title="No suppliers" text="Register a supplier, then complete its governed evaluation before approval." />}
      {governedSupplier ? <SupplierGovernancePanel amoCode={amoCode()} supplier={governedSupplier} canQuality={canQuality} currentUserId={currentUserId} onClose={() => setGovernedSupplierId(null)} onChanged={onChanged} /> : null}
    </section>
  );
}

export function Control({ holds, orders, receipts, canQuality, canFinance, openModal, linkDocument }: {
  holds: ProcurementQualityHold[]; orders: ProcurementPurchaseOrder[]; receipts: ProcurementReceipt[]; canQuality: boolean; canFinance: boolean; openModal: OpenModal; linkDocument: LinkDocument;
}) {
  return (
    <div className="proc-stack">
      <section className="proc-panel">
        <header className="proc-section-heading proc-section-heading--split"><div><h2>Quality holds</h2><p>Supplier, purchase-order, and receipt holds have an enforceable release veto.</p></div>{canQuality ? <button type="button" className="proc-button proc-button--danger" onClick={() => openModal("hold")}><ShieldAlert size={16} />Place hold</button> : null}</header>
        {holds.length ? <div className="proc-card-list">{holds.map((item) => <article key={item.id}><div><strong>{item.hold_number}</strong><span>{item.reason}</span><small>{item.target_type} #{item.target_id} · {item.qms_finding_id || item.qms_car_id || "No QMS reference"}</small></div><Status value={item.status} /><RecordActions><button type="button" onClick={() => linkDocument("QUALITY_HOLD", item.id)}><Paperclip size={14} />Evidence</button>{canQuality && item.status === "ACTIVE" ? <button type="button" onClick={() => openModal("holdRelease", { holdId: String(item.id) })}>Release hold</button> : null}</RecordActions></article>)}</div> : <Empty icon={ShieldCheck} title="No Quality holds" text="No active supplier, order, or receipt veto is recorded." />}
      </section>
      <section className="proc-command-grid">
        <div className="proc-panel"><header><div><h2>Quarantine workload</h2><p>{receipts.length} receipt{receipts.length === 1 ? "" : "s"} waiting for inspection or release.</p></div></header><button type="button" className="proc-button proc-button--secondary" onClick={() => openModal("inspection")}>Open inspection</button></div>
        <div className="proc-panel"><header><div><h2>Finance reconciliation</h2><p>Three-way match uses ordered value and Quality-released receipt quantities.</p></div></header>{canFinance ? <button type="button" className="proc-button proc-button--primary" onClick={() => openModal("match", { tolerance: "0.01" })}><CircleDollarSign size={16} />Run invoice match</button> : <span className="proc-muted">Finance role required.</span>}<small>{orders.length} purchase order{orders.length === 1 ? "" : "s"} available for reconciliation.</small></div>
      </section>
    </div>
  );
}
