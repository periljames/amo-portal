export const QMS_WORKSPACE_PURPOSE: Record<string, string> = {
  inbox: "Prioritise your assignments, approvals and overdue Quality work.",
  calendar: "Plan dated Quality work and review upcoming commitments.",
  audits: "Plan audits, conduct fieldwork and follow findings through closure.",
  findings: "Investigate findings and follow their corrective actions.",
  cars: "Track responses, corrective actions, review and effectiveness.",
  risk: "Review exposure, treatment plans and opportunities for improvement.",
  "change-control": "Review proposed changes, approvals and implementation.",
  system: "Maintain the QMS scope, processes and Quality objectives.",
  documents: "Find controlled documents and follow their approval and distribution.",
  suppliers: "Manage provider qualification, agreements, approval and oversight.",
  "provider-access": "Invite vendor representatives and govern their access.",
  "equipment-calibration": "Review equipment readiness, calibration deadlines and certificates.",
  "external-interface": "Track authority correspondence, customer feedback and response commitments.",
  "management-review": "Prepare management reviews and follow decisions and actions.",
  reports: "Review Quality performance and open the underlying work for investigation.",
  "evidence-vault": "Find retained evidence and open its governed source record.",
  "mail-identity": "Configure the sender, reply addresses and delivery readiness.",
  settings: "Manage Quality configuration and the workspaces that own it.",
  aerodoc: "Open controlled document and compliance tools.",
};

export const qmsViewLabel = (view: string): string => ({
  "qms-scope": "QMS scope", "assigned-to-me": "Assigned to me", "supplier-audits": "Provider audits", "supplier-findings": "Provider findings",
  "risk-register": "Risk register", "out-of-tolerance": "Out of tolerance", "executive-dashboard": "Executive overview",
  "immutable-archive": "Retained archive", "new": "Create", "register": "Register",
}[view] || view.replaceAll("-", " ").replace(/^./, letter => letter.toUpperCase()));
