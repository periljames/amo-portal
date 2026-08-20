import type { ComponentType } from "react";
import {
  ClipboardCheck,
  FileText,
  HandCoins,
  Paperclip,
  ShieldCheck,
  ShoppingCart,
  Truck,
  UsersRound,
} from "lucide-react";

import type {
  ProcurementDashboard,
  ProcurementPurchaseOrder,
  ProcurementQualityHold,
  ProcurementQuote,
  ProcurementReceipt,
  ProcurementReferenceData,
  ProcurementRequisition,
  ProcurementRFQ,
  ProcurementSupplier,
} from "../../types/procurement";

export type Section = "command" | "requests" | "sourcing" | "orders" | "receiving" | "suppliers" | "control" | "documents";
export type Modal =
  | "requisition"
  | "supplier"
  | "scope"
  | "rfq"
  | "quote"
  | "quoteEvaluation"
  | "po"
  | "poApproval"
  | "receipt"
  | "inspection"
  | "receiptRelease"
  | "hold"
  | "holdRelease"
  | "match"
  | null;
export type FormState = Record<string, string | boolean>;
export type WorkspaceData = {
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

export const EMPTY: WorkspaceData = {
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

export const NAV: Array<{ id: Section; label: string; icon: ComponentType<{ size?: number }> }> = [
  { id: "command", label: "Command", icon: ClipboardCheck },
  { id: "requests", label: "Requests", icon: FileText },
  { id: "sourcing", label: "Sourcing", icon: HandCoins },
  { id: "orders", label: "Orders", icon: ShoppingCart },
  { id: "receiving", label: "Receiving", icon: Truck },
  { id: "suppliers", label: "Suppliers", icon: UsersRound },
  { id: "control", label: "Quality Control", icon: ShieldCheck },
  { id: "documents", label: "Documents", icon: Paperclip },
];

export function humanize(value?: string | null): string {
  return (value || "—")
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function money(value: string | number, currency = "USD"): string {
  const amount = Number(value || 0);
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(Number.isFinite(amount) ? amount : 0);
}

export function dateLabel(value?: string | null): string {
  if (!value) return "Not set";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(parsed);
}

export function badgeClass(value?: string | null): string {
  const status = (value || "").toUpperCase();
  if (/REJECT|SUSPEND|EXPIRE|CANCEL|BLOCK|VOID/.test(status)) return "proc-badge--danger";
  if (/QUARANTINE|PENDING|REVIEW|HOLD|CONDITION|VARIANCE|AOG|URGENT/.test(status)) return "proc-badge--warning";
  if (/APPROVED|ACCEPTED|RELEASED|FULFILLED|MATCHED|CLOSED|ACTIVE/.test(status)) return "proc-badge--success";
  return "proc-badge--info";
}
