import { authHeaders } from "./auth";
import { apiGet, apiPost } from "./crs";
import { qmsListAudits, type QMSAuditOut } from "./qms";

export type DashboardFilter = {
  auditor: string;
  dateRange: string;
};

export type KpiMetric = {
  label: string;
  value: number;
  changePct: number;
};

export type DonutDatum = { name: string; value: number };

export type TrendDatum = {
  month: string;
  tasks: number;
  defects: number;
  samples: number;
};

export type CockpitPayload = {
  qualityScore: number;
  kpis: KpiMetric[];
  fatalBySupervisor: DonutDatum[];
  fatalByLocation: DonutDatum[];
  trends: TrendDatum[];
};

export type AircraftOption = {
  tailNumber: string;
  engineHours: number;
  engineCycles: number;
};

export type WorkScope =
  | "Maintenance"
  | "Quality"
  | "Safety"
  | "Reliability"
  | "Training"
  | "Engineering";

export type CalendarItem = {
  id: string;
  title: string;
  startsAt: string;
  endsAt: string;
  viewDate: string;
  endDate?: string;
  assignedPersonnel: string[];
  location: string;
  detail: string;
  source: "Internal" | "Outlook" | "Google";
  lastSyncedAt: string;
  resourceGroup: string;
  severity: "standard" | "priority" | "critical";
  scope: WorkScope;
  route?: string;
};

const MOCK_COCKPIT: CockpitPayload = {
  qualityScore: 92,
  kpis: [
    { label: "Total Tasks", value: 428, changePct: 7.5 },
    { label: "Samples", value: 121, changePct: 4.2 },
    { label: "Defects", value: 34, changePct: -3.4 },
    { label: "Fatal Errors", value: 6, changePct: -11.8 },
  ],
  fatalBySupervisor: [
    { name: "M. Otieno", value: 2 },
    { name: "S. Karanja", value: 3 },
    { name: "A. Noor", value: 1 },
  ],
  fatalByLocation: [
    { name: "Hangar A", value: 2 },
    { name: "Hangar B", value: 1 },
    { name: "Line Station", value: 3 },
  ],
  trends: [
    { month: "Jan", tasks: 61, defects: 8, samples: 13 },
    { month: "Feb", tasks: 67, defects: 7, samples: 16 },
    { month: "Mar", tasks: 72, defects: 6, samples: 17 },
    { month: "Apr", tasks: 64, defects: 4, samples: 19 },
    { month: "May", tasks: 80, defects: 5, samples: 21 },
    { month: "Jun", tasks: 84, defects: 4, samples: 22 },
  ],
};

export async function fetchCockpitData(filters: DashboardFilter): Promise<CockpitPayload> {
  try {
    const params = new URLSearchParams({ auditor: filters.auditor, date_range: filters.dateRange });
    return await apiGet<CockpitPayload>(`/qms/cockpit?${params.toString()}`, { headers: authHeaders() });
  } catch {
    return MOCK_COCKPIT;
  }
}

export async function listAircraftOptions(): Promise<AircraftOption[]> {
  try {
    return await apiGet<AircraftOption[]>("/crs/aircraft/options", { headers: authHeaders() });
  } catch {
    return [
      { tailNumber: "5Y-SLA", engineHours: 1842, engineCycles: 1110 },
      { tailNumber: "5Y-SLB", engineHours: 2184, engineCycles: 1312 },
      { tailNumber: "5Y-SLC", engineHours: 931, engineCycles: 665 },
    ];
  }
}

export async function fetchSerialNumber(): Promise<string> {
  try {
    const result = await apiGet<{ serial: string }>("/crs/serial/next", { headers: authHeaders() });
    return result.serial;
  } catch {
    return `CRS-${new Date().getFullYear()}-${Math.floor(1000 + Math.random() * 9000)}`;
  }
}

const mapAuditToCalendarItem = (audit: QMSAuditOut): CalendarItem | null => {
  if (!audit.planned_start) return null;

  const statusSeverity: CalendarItem["severity"] =
    audit.status === "CAP_OPEN" ? "critical" : audit.status === "IN_PROGRESS" ? "priority" : "standard";

  return {
    id: `audit-${audit.id}`,
    title: audit.title || audit.audit_ref,
    startsAt: "08:00",
    endsAt: "17:00",
    viewDate: audit.planned_start,
    endDate: audit.planned_end || undefined,
    assignedPersonnel: [audit.auditee || "Audit team"],
    location: "Quality audit",
    detail: audit.scope || audit.criteria || `Audit ${audit.audit_ref}`,
    source: "Internal",
    lastSyncedAt: audit.updated_at,
    resourceGroup: "Audit Program",
    severity: statusSeverity,
    scope: "Quality",
    route: `/qms/audits/${audit.id}`,
  };
};

export async function fetchCalendarEvents(filters: DashboardFilter): Promise<CalendarItem[]> {
  const params = new URLSearchParams({ auditor: filters.auditor, date_range: filters.dateRange });

  try {
    const [calendarEvents, audits] = await Promise.all([
      apiGet<CalendarItem[]>(`/qms/maintenance-calendar?${params.toString()}`, { headers: authHeaders() }),
      qmsListAudits({}),
    ]);

    const auditEvents = audits.map(mapAuditToCalendarItem).filter((item): item is CalendarItem => item !== null);
    return [...calendarEvents, ...auditEvents];
  } catch {
    let auditFallback: CalendarItem[] = [];
    try {
      const audits = await qmsListAudits({});
      auditFallback = audits.map(mapAuditToCalendarItem).filter((item): item is CalendarItem => item !== null);
    } catch {
      auditFallback = [];
    }

    return [
      {
        id: "1",
        title: "A-check - Dash 8",
        startsAt: "09:00",
        endsAt: "11:30",
        viewDate: "2026-02-11",
        endDate: "2026-02-12",
        assignedPersonnel: ["Inspector Njoroge", "Eng. Mwikali"],
        location: "Hangar A",
        detail: "Routine A-check and paperwork verification.",
        source: "Internal",
        lastSyncedAt: "2026-02-11T08:45:00Z",
        resourceGroup: "Hangar Slot A",
        severity: "priority",
        scope: "Maintenance",
      },
      {
        id: "2",
        title: "CAR follow-up",
        startsAt: "13:00",
        endsAt: "14:00",
        viewDate: "2026-02-12",
        assignedPersonnel: ["QA Manager", "Shift Supervisor"],
        location: "QA Office",
        detail: "Close open corrective actions for line maintenance findings.",
        source: "Outlook",
        lastSyncedAt: "2026-02-11T09:00:00Z",
        resourceGroup: "Quality Team",
        severity: "standard",
        scope: "Quality",
      },
      {
        id: "3",
        title: "B-check prep brief",
        startsAt: "16:15",
        endsAt: "17:10",
        viewDate: "2026-02-12",
        endDate: "2026-02-14",
        assignedPersonnel: ["Chief Engineer", "Shift Lead"],
        location: "Hangar B",
        detail: "Risk and tooling brief before overnight B-check package.",
        source: "Google",
        lastSyncedAt: "2026-02-11T09:02:00Z",
        resourceGroup: "Hangar Slot B",
        severity: "critical",
        scope: "Engineering",
      },
      {
        id: "4",
        title: "Safety stand-down",
        startsAt: "10:00",
        endsAt: "11:00",
        viewDate: "2026-02-13",
        assignedPersonnel: ["Safety Manager", "Line Supervisors"],
        location: "Briefing Room",
        detail: "Mandatory safety briefing after ramp incident report.",
        source: "Internal",
        lastSyncedAt: "2026-02-11T09:04:00Z",
        resourceGroup: "Safety Team",
        severity: "priority",
        scope: "Safety",
      },
      {
        id: "5",
        title: "Reliability review",
        startsAt: "14:30",
        endsAt: "15:30",
        viewDate: "2026-02-13",
        assignedPersonnel: ["Reliability Lead", "Data Analyst"],
        location: "Ops Analytics Desk",
        detail: "Monthly trend review for delayed defects and repeats.",
        source: "Google",
        lastSyncedAt: "2026-02-11T09:07:00Z",
        resourceGroup: "Reliability Cell",
        severity: "standard",
        scope: "Reliability",
      },
      {
        id: "6",
        title: "Part 145 competency check",
        startsAt: "08:30",
        endsAt: "10:30",
        viewDate: "2026-02-14",
        endDate: "2026-02-15",
        assignedPersonnel: ["Training Officer", "Certifying Engineers"],
        location: "Training Bay",
        detail: "Competency recurrency assessment and practical checks.",
        source: "Outlook",
        lastSyncedAt: "2026-02-11T09:10:00Z",
        resourceGroup: "Training Team",
        severity: "priority",
        scope: "Training",
      },
      ...auditFallback,
    ];
  }
}

export async function submitCrsForm(payload: Record<string, unknown>) {
  return apiPost("/crs/", payload, { headers: authHeaders() });
}
