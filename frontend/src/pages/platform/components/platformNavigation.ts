import "./platformModeRuntime";
import "./platformUxRuntime";

export type PlatformNavItem = {
  to: string;
  label: string;
  mark: string;
  description: string;
  badgeKey?: string;
};

export type PlatformNavSection = {
  label: string;
  items: PlatformNavItem[];
};

export const platformNavSections: PlatformNavSection[] = [
  {
    label: "Platform",
    items: [
      { to: "/platform/control", label: "Overview", mark: "OV", description: "Health, trends and priority work" },
      { to: "/platform/tenants", label: "Tenants & Institutions", mark: "TI", description: "Provision and control tenants", badgeKey: "active_tenants" },
      { to: "/platform/users", label: "Global User Hub", mark: "UH", description: "Users, access and sessions", badgeKey: "total_users" },
      { to: "/platform/analytics", label: "Platform Analytics", mark: "AN", description: "Traffic, latency and usage" },
    ],
  },
  {
    label: "Products",
    items: [
      { to: "/platform/billing?tab=modules", label: "Module Catalog", mark: "MC", description: "Modules and availability" },
      { to: "/platform/billing?tab=plans", label: "Plans & Bundles", mark: "PB", description: "Plans and included modules" },
      { to: "/platform/billing?tab=price-books", label: "Price Books", mark: "BK", description: "Markets, currency and tax" },
      { to: "/platform/billing?tab=prices", label: "Versioned Prices", mark: "VP", description: "Effective prices and mappings" },
    ],
  },
  {
    label: "Commercial",
    items: [
      { to: "/platform/billing?tab=overview", label: "Commercial Overview", mark: "CO", description: "Revenue, balance and risk", badgeKey: "overdue_invoices" },
      { to: "/platform/billing?tab=subscriptions", label: "Subscriptions", mark: "SU", description: "Plans, terms and renewals" },
      { to: "/platform/billing?tab=invoices", label: "Invoices", mark: "IN", description: "Line items and balances" },
      { to: "/platform/billing?tab=payments", label: "Payments", mark: "PY", description: "Evidence and reconciliation" },
    ],
  },
  {
    label: "Management",
    items: [
      { to: "/platform/integrations", label: "Integrations & API", mark: "IA", description: "Providers, webhooks and keys", badgeKey: "configured_providers" },
      { to: "/platform/infrastructure", label: "System Infrastructure", mark: "SI", description: "Workers, flags and maintenance", badgeKey: "queue_depth" },
      { to: "/platform/security", label: "Security & Compliance", mark: "SC", description: "Alerts, controls and evidence", badgeKey: "critical_security_alerts" },
      { to: "/platform/security?tab=audit", label: "Audit Logs", mark: "AL", description: "Privileged activity trail" },
    ],
  },
  {
    label: "Support & tools",
    items: [
      { to: "/platform/integrations?tab=support", label: "Support Center", mark: "SP", description: "Tickets, notes and drafts", badgeKey: "open_support_tickets" },
      { to: "/platform/integrations?tab=webhooks", label: "Webhook Inspector", mark: "WH", description: "Endpoints and deliveries" },
      { to: "/platform/integrations?tab=email", label: "Email Delivery", mark: "EM", description: "Resend health and domains" },
      { to: "/platform/integrations?tab=providers", label: "Provider Registry", mark: "PR", description: "External service controls" },
    ],
  },
];

export const platformNav = platformNavSections.flatMap((section) => section.items);
