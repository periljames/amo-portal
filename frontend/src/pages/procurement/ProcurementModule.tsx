import React, { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { AlertTriangle, ChevronRight, LoaderCircle, PackageCheck, Plus, RefreshCw, Search, ShieldAlert, UsersRound } from "lucide-react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { useToast } from "../../components/feedback/ToastProvider";
import { getCachedUser } from "../../services/auth";
import { getProcurementDashboard, getProcurementReferenceData, listProcurementPurchaseOrders, listProcurementQualityHolds, listProcurementQuotes, listProcurementReceipts, listProcurementRequisitions, listProcurementRfqs, listProcurementSuppliers } from "../../services/procurement";
import type { ProcurementDocumentEntityType, ProcurementRequisition } from "../../types/procurement";
import { submitProcurementForm } from "./procurementActions";
import ProcurementDocumentCenter from "./ProcurementDocumentCenter";
import { Command, Control, Orders, Receiving, Requests, Sourcing, Suppliers } from "./ProcurementSections";
import { renderFields } from "./ProcurementForms";
import { ModalShell } from "./procurementUiShared";
import { EMPTY, NAV, dateLabel, humanize, type FormState, type Modal, type Section, type WorkspaceData } from "./procurementUiModel";
import "../../styles/procurement.css";

const QUALITY_ROLES = new Set(["QUALITY_MANAGER", "QUALITY_INSPECTOR", "AMO_ADMIN", "SUPERUSER"]);
const FINANCE_ROLES = new Set(["FINANCE_MANAGER", "ACCOUNTS_OFFICER", "AMO_ADMIN", "SUPERUSER"]);
const DOCUMENT_CONTROL_ROLES = new Set(["PROCUREMENT_OFFICER", "QUALITY_MANAGER", "QUALITY_INSPECTOR", "AMO_ADMIN", "SUPERUSER"]);

export default function ProcurementModule() {
  const { amoCode = "" } = useParams<{ amoCode: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const { pushToast } = useToast();
  const user = getCachedUser();
  const role = user?.role || "";
  const canQuality = QUALITY_ROLES.has(role) || Boolean(user?.is_superuser);
  const canFinance = FINANCE_ROLES.has(role) || Boolean(user?.is_superuser);
  const canDocumentControl = DOCUMENT_CONTROL_ROLES.has(role) || Boolean(user?.is_superuser);

  const rawSection = location.pathname.split("/").filter(Boolean)[3] as Section | undefined;
  const section: Section = NAV.some((item) => item.id === rawSection) ? rawSection! : "command";
  const [data, setData] = useState<WorkspaceData>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [partialErrors, setPartialErrors] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [modal, setModal] = useState<Modal>(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<FormState>({});
  const [documentTarget, setDocumentTarget] = useState<{ type: ProcurementDocumentEntityType; id: string } | null>(null);

  const go = useCallback((next: Section) => {
    navigate(`/maintenance/${encodeURIComponent(amoCode)}/procurement/${next}`);
  }, [amoCode, navigate]);

  const load = useCallback(async (announce = false) => {
    if (announce) setRefreshing(true); else setLoading(true);
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
    const settled = await Promise.allSettled(jobs.map(([, promise]) => promise));
    const errors: string[] = [];
    setData((current) => {
      const next = { ...current } as WorkspaceData;
      settled.forEach((result, index) => {
        const key = jobs[index][0] as keyof WorkspaceData;
        if (result.status === "fulfilled") (next as Record<string, unknown>)[key] = result.value;
        else errors.push(`${humanize(key)}: ${result.reason instanceof Error ? result.reason.message : "unavailable"}`);
      });
      return next;
    });
    setPartialErrors(errors);
    setLoading(false);
    setRefreshing(false);
    if (announce) {
      pushToast({
        title: errors.length ? "Procurement refreshed with warnings" : "Procurement refreshed",
        message: errors.length ? `${errors.length} data source${errors.length === 1 ? "" : "s"} could not be refreshed.` : "Operational data is current.",
        variant: errors.length ? "warning" : "success",
        sound: true,
      });
    }
  }, [amoCode, pushToast]);

  useEffect(() => { void load(); }, [load]);

  const setValue = (name: string, value: string | boolean) => setForm((current) => ({ ...current, [name]: value }));
  const openModal = (next: Exclude<Modal, null>, initial: FormState = {}) => { setForm(initial); setModal(next); };
  const closeModal = () => { if (!saving) { setModal(null); setForm({}); } };
  const linkDocument = (type: ProcurementDocumentEntityType, id: number) => { setDocumentTarget({ type, id: String(id) }); go("documents"); };

  const act = async (label: string, operation: () => Promise<unknown>, success = `${label} completed`) => {
    setSaving(true);
    try {
      await operation();
      pushToast({ title: success, message: `${label} completed and the audit trail was updated.`, variant: "success", sound: true });
      await load();
    } catch (caught) {
      pushToast({ title: `${label} failed`, message: caught instanceof Error ? caught.message : "The controlled action could not be completed.", variant: "error", sound: true, duration: 8000 });
    } finally {
      setSaving(false);
    }
  };

  const filtered = <T,>(items: T[], text: (item: T) => string): T[] => {
    const needle = query.trim().toLowerCase();
    return needle ? items.filter((item) => text(item).toLowerCase().includes(needle)) : items;
  };

  const counts: Record<Section, number> = {
    command: 0,
    requests: data.requisitions.length,
    sourcing: data.rfqs.length + data.quotes.length,
    orders: data.orders.length,
    receiving: data.receipts.length,
    suppliers: data.suppliers.length,
    control: data.holds.length,
    documents: 0,
  };

  const quarantine = data.receipts.filter((item) => ["QUARANTINED", "DOCUMENT_REVIEW", "PHYSICAL_INSPECTION", "ACCEPTED_PENDING_RELEASE"].includes(item.status));
  const aog = data.requisitions.filter((item) => item.priority === "AOG" && !["CLOSED", "CANCELLED", "REJECTED"].includes(item.status));
  const restrictedSuppliers = data.suppliers.filter((item) => ["RESTRICTED", "SUSPENDED", "EXPIRED", "REJECTED"].includes(item.status));
  const activeHolds = data.holds.filter((item) => item.status === "ACTIVE");

  const alertCards = [
    activeHolds.length ? { title: `${activeHolds.length} active Quality hold${activeHolds.length === 1 ? "" : "s"}`, text: "Release, award, and invoice controls remain blocked.", tone: "danger", icon: ShieldAlert, target: "control" as Section } : null,
    aog.length ? { title: `${aog.length} AOG demand${aog.length === 1 ? "" : "s"}`, text: "Immediate sourcing attention is required.", tone: "danger", icon: AlertTriangle, target: "requests" as Section } : null,
    quarantine.length ? { title: `${quarantine.length} receipt${quarantine.length === 1 ? "" : "s"} in quarantine`, text: "Inspection and independent Quality release are pending.", tone: "warning", icon: PackageCheck, target: "receiving" as Section } : null,
    restrictedSuppliers.length ? { title: `${restrictedSuppliers.length} restricted supplier${restrictedSuppliers.length === 1 ? "" : "s"}`, text: "Awards are blocked unless a controlled override is authorized.", tone: "warning", icon: UsersRound, target: "suppliers" as Section } : null,
  ].filter(Boolean) as Array<{ title: string; text: string; tone: string; icon: React.ComponentType<{ size?: number }>; target: Section }>;

  const searchBox = section !== "command" && section !== "documents" ? (
    <label className="proc-search-box"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`Search ${NAV.find((item) => item.id === section)?.label.toLowerCase()}`} /></label>
  ) : null;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!modal) return;
    setSaving(true);
    try {
      const created = await submitProcurementForm(amoCode, modal, form, data);
      pushToast({ title: `${humanize(modal)} saved`, message: "The controlled record and audit event were saved.", variant: "success", sound: true });
      if (modal === "requisition" && created && typeof created === "object" && "id" in created) {
        setDocumentTarget({ type: "REQUISITION", id: String((created as ProcurementRequisition).id) });
      }
      setModal(null);
      setForm({});
      await load();
    } catch (caught) {
      pushToast({ title: `${humanize(modal)} failed`, message: caught instanceof Error ? caught.message : "The record could not be saved.", variant: "error", sound: true, duration: 8000 });
    } finally {
      setSaving(false);
    }
  };

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="procurement">
      <div className="proc-page">
        <header className="proc-module-header">
          <div><span className="proc-eyebrow">Aviation supply chain control</span><h1>Procurement & Supply Chain</h1><p>Controlled demand, sourcing, purchasing, quarantine, Quality release, supplier approval, and retained evidence.</p></div>
          <div className="proc-header-actions">
            <span className="proc-live"><span />Tenant controls active</span>
            <span className="proc-sync">{data.dashboard?.as_of ? `Updated ${dateLabel(data.dashboard.as_of)}` : "Awaiting data"}</span>
            <button type="button" className="proc-button proc-button--secondary" onClick={() => void load(true)} disabled={refreshing}>{refreshing ? <LoaderCircle className="is-spinning" size={16} /> : <RefreshCw size={16} />}Refresh</button>
            <button type="button" className="proc-button proc-button--primary" onClick={() => openModal("requisition", { priority: "ROUTINE", quantity: "1", department: "MAINTENANCE" })}><Plus size={16} />New request</button>
          </div>
        </header>

        <nav className="proc-tabs" aria-label="Procurement work areas">
          {NAV.map(({ id, label, icon: Icon }) => (
            <button key={id} type="button" className={section === id ? "is-active" : ""} onClick={() => go(id)} aria-current={section === id ? "page" : undefined}>
              <Icon size={16} /><span>{label}</span>{counts[id] ? <small>{counts[id]}</small> : null}
            </button>
          ))}
        </nav>

        {partialErrors.length ? <div className="proc-message proc-message--warning" role="alert"><AlertTriangle size={18} /><span>Some Procurement data could not be loaded. Available work remains usable: {partialErrors.join(" · ")}</span><button type="button" onClick={() => void load(true)}>Retry</button></div> : null}

        {alertCards.length ? (
          <div className="proc-alert-ribbon" aria-label="Procurement warnings">
            {alertCards.map(({ title, text, tone, icon: Icon, target }) => (
              <button type="button" key={title} className={`proc-alert-card proc-alert-card--${tone}`} onClick={() => go(target)}>
                <Icon size={20} /><div><strong>{title}</strong><span>{text}</span></div><ChevronRight size={17} />
              </button>
            ))}
          </div>
        ) : null}

        <main className="proc-content">
          {section === "command" ? <Command data={data} loading={loading} go={go} openModal={openModal} /> : null}
          {section === "requests" ? <Requests items={filtered(data.requisitions, (item) => `${item.requisition_number} ${item.title} ${item.requesting_department} ${item.status}`)} loading={loading} search={searchBox} openModal={openModal} linkDocument={linkDocument} act={act} /> : null}
          {section === "sourcing" ? <Sourcing rfqs={filtered(data.rfqs, (item) => `${item.rfq_number} ${item.title} ${item.status}`)} quotes={filtered(data.quotes, (item) => `${item.quote_reference} ${item.status}`)} loading={loading} search={searchBox} openModal={openModal} linkDocument={linkDocument} /> : null}
          {section === "orders" ? <Orders items={filtered(data.orders, (item) => `${item.po_number} ${item.status} ${item.supplier_id}`)} loading={loading} search={searchBox} openModal={openModal} linkDocument={linkDocument} act={act} /> : null}
          {section === "receiving" ? <Receiving items={filtered(data.receipts, (item) => `${item.receipt_number} ${item.status} ${item.delivery_note_number || ""}`)} loading={loading} search={searchBox} canQuality={canQuality} openModal={openModal} linkDocument={linkDocument} /> : null}
          {section === "suppliers" ? <Suppliers items={filtered(data.suppliers, (item) => `${item.supplier_code} ${item.legal_name} ${item.status} ${item.country || ""}`)} loading={loading} search={searchBox} openModal={openModal} linkDocument={linkDocument} canQuality={canQuality} currentUserId={user?.id || null} onChanged={async () => { await load(); }} /> : null}
          {section === "control" ? <Control holds={data.holds} orders={data.orders} receipts={quarantine} canQuality={canQuality} canFinance={canFinance} openModal={openModal} linkDocument={linkDocument} /> : null}
          {section === "documents" ? <ProcurementDocumentCenter amoCode={amoCode} records={{ requisitions: data.requisitions, rfqs: data.rfqs, quotes: data.quotes, orders: data.orders, receipts: data.receipts, suppliers: data.suppliers, holds: data.holds }} initialEntity={documentTarget} canQuality={canQuality} canControl={canDocumentControl} currentUserId={user?.id || null} /> : null}
        </main>

        {modal ? <ModalShell title={humanize(modal)} busy={saving} onClose={closeModal} onSubmit={submit}>{renderFields(modal, form, setValue, data)}</ModalShell> : null}
      </div>
    </DepartmentLayout>
  );
}
