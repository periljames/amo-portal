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
      { to: "/platform/control", label: "Overview", mark: "OV", description: "Health, work queue and platform status" },
      { to: "/platform/tenants", label: "Tenants & Institutions", mark: "TI", description: "Tenant lifecycle, access and modules", badgeKey: "active_tenants" },
      { to: "/platform/users", label: "Global User Hub", mark: "UH", description: "Users, sessions and account controls", badgeKey: "total_users" },
      { to: "/platform/billing", label: "Subscription & Billing", mark: "BI", description: "Plans, invoices, fiscalization and revenue", badgeKey: "overdue_invoices" },
      { to: "/platform/analytics", label: "Platform Analytics", mark: "AN", description: "Traffic, latency, usage and tenant load" },
    ],
  },
  {
    label: "Management",
    items: [
      { to: "/platform/integrations", label: "Integrations & API", mark: "IA", description: "Providers, email, webhooks and API keys", badgeKey: "configured_providers" },
      { to: "/platform/control?tab=ai", label: "AI Control Centre", mark: "AI", description: "Live model testing, tenant policy and usage metering" },
      { to: "/platform/infrastructure", label: "System Infrastructure", mark: "SI", description: "Workers, maintenance, flags and diagnostics", badgeKey: "queue_depth" },
      { to: "/platform/network", label: "Network Diagnostics", mark: "NW", description: "Speed tests, latency and SLA history" },
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
