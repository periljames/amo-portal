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
      { to: "/platform/control", label: "Overview", mark: "OV", description: "Health, live trends, work queue and platform status" },
      { to: "/platform/tenants", label: "Tenants & Institutions", mark: "TI", description: "Provisioning, profiles, users, modules and tenant controls", badgeKey: "active_tenants" },
      { to: "/platform/users", label: "Global User Hub", mark: "UH", description: "Users, sessions, onboarding and security controls", badgeKey: "total_users" },
      { to: "/platform/analytics", label: "Platform Analytics", mark: "AN", description: "Traffic, latency, bandwidth, usage and tenant load" },
    ],
  },
  {
    label: "Products",
    items: [
      { to: "/platform/billing?tab=modules", label: "Module Catalog", mark: "MC", description: "Canonical modules, routes, dependencies and availability" },
      { to: "/platform/billing?tab=plans", label: "Plans & Bundles", mark: "PB", description: "Product plans, included modules and trial policy" },
      { to: "/platform/billing?tab=price-books", label: "Price Books", mark: "BK", description: "REAL or DEMO markets, currencies and tax basis" },
      { to: "/platform/billing?tab=prices", label: "Versioned Prices", mark: "VP", description: "Effective prices and external provider mappings" },
    ],
  },
  {
    label: "Commercial",
    items: [
      { to: "/platform/billing?tab=overview", label: "Commercial Overview", mark: "CO", description: "Revenue by currency, outstanding balance and risk", badgeKey: "overdue_invoices" },
      { to: "/platform/billing?tab=subscriptions", label: "Subscriptions", mark: "SU", description: "Trials, renewals, plans, terms and reconciliation" },
      { to: "/platform/billing?tab=invoices", label: "Invoices", mark: "IN", description: "Structured line items, balances and fiscal state" },
      { to: "/platform/billing?tab=payments", label: "Payments", mark: "PY", description: "Payment evidence, ledger entries and reconciliation" },
    ],
  },
  {
    label: "Management",
    items: [
      { to: "/platform/integrations", label: "Integrations & API", mark: "IA", description: "Providers, email, webhooks and API keys", badgeKey: "configured_providers" },
      { to: "/platform/infrastructure", label: "System Infrastructure", mark: "SI", description: "Workers, maintenance, flags and diagnostics", badgeKey: "queue_depth" },
      { to: "/platform/security", label: "Security & Compliance", mark: "SC", description: "Alerts, policy controls and audit evidence", badgeKey: "critical_security_alerts" },
      { to: "/platform/security?tab=audit", label: "Audit Logs", mark: "AL", description: "Privileged and platform activity trail" },
    ],
  },
  {
    label: "Support & tools",
    items: [
      { to: "/platform/integrations?tab=support", label: "Support Center", mark: "SP", description: "Tenant tickets, internal notes and AI drafts", badgeKey: "open_support_tickets" },
      { to: "/platform/integrations?tab=webhooks", label: "Webhook Inspector", mark: "WH", description: "Endpoints, delivery state and signing" },
      { to: "/platform/integrations?tab=email", label: "Email Delivery", mark: "EM", description: "Resend health, domains and templates" },
      { to: "/platform/integrations?tab=providers", label: "Provider Registry", mark: "PR", description: "Payments, tax, AI and external services" },
    ],
  },
];

export const platformNav = platformNavSections.flatMap((section) => section.items);
