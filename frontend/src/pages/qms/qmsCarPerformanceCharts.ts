import type { CAROut, QMSAuditRegisterRowOut } from "../../services/qms";

export const QMS_CLOSURE_TARGET = 80;

export type ChartDatum = { name: string; value: number; fill?: string };

export type DepartmentExposureDatum = {
  department: string;
  open: number;
  overdue: number;
  total: number;
};

export type FindingConversionDatum = {
  name: string;
  value: number;
  fill: string;
};

export type OverdueAgingDatum = {
  bucket: string;
  count: number;
};

export type ClosureForecast = {
  openCount: number;
  historicalOnTimeRate: number | null;
  expectedOnTimeClosures: number | null;
  methodology: string;
};

function dateOnly(value: string | null | undefined): string | null {
  if (!value) return null;
  const clean = String(value).slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(clean) ? clean : null;
}

export function agreedDue(car: CAROut): string | null {
  return dateOnly(car.target_closure_date) || dateOnly(car.due_date);
}

export function closedDate(car: CAROut): string | null {
  return dateOnly(car.date_closed) || dateOnly(car.closed_at);
}

export function isClosed(car: CAROut): boolean {
  return car.status === "CLOSED";
}

export function isOpen(car: CAROut): boolean {
  return !["CLOSED", "CANCELLED"].includes(car.status);
}

export function isInReview(car: CAROut): boolean {
  return (
    car.status === "PENDING_VERIFICATION"
    || car.root_cause_status === "SUBMITTED"
    || car.capa_status === "SUBMITTED"
    || car.capa_status === "NEEDS_EVIDENCE"
  );
}

export function isOverdue(car: CAROut, today: string): boolean {
  const due = agreedDue(car);
  return Boolean(isOpen(car) && due && due < today);
}

export function isMeasurableClosure(car: CAROut): boolean {
  return Boolean(isClosed(car) && agreedDue(car) && closedDate(car));
}

export function isOnTimeClosure(car: CAROut): boolean {
  const due = agreedDue(car);
  const closed = closedDate(car);
  return Boolean(isClosed(car) && due && closed && closed <= due);
}

export function departmentLabel(car: CAROut): string {
  return car.responsible_department?.trim() || "Unassigned";
}

export function buildQpiChartData(onTimePercent: number | null, target = QMS_CLOSURE_TARGET): ChartDatum[] {
  const actual = onTimePercent == null ? 0 : Number(onTimePercent.toFixed(1));
  return [
    { name: "On-time %", value: actual, fill: actual >= target ? "var(--accent-success, #22c55e)" : "var(--accent-warning, #f59e0b)" },
    { name: "Target", value: target, fill: "var(--accent-primary, #3b82f6)" },
  ];
}

export function buildWorkloadChartData(metrics: {
  open: number;
  overdue: number;
  review: number;
  closed: number;
}): ChartDatum[] {
  return [
    { name: "Open", value: metrics.open, fill: "var(--accent-primary, #2563eb)" },
    { name: "Overdue", value: metrics.overdue, fill: "var(--accent-danger, #dc2626)" },
    { name: "Review", value: metrics.review, fill: "var(--accent-warning, #d97706)" },
    { name: "Closed", value: metrics.closed, fill: "var(--accent-success, #15803d)" },
  ];
}

export function buildDepartmentExposureData(
  cars: CAROut[],
  today: string,
  limit = 8,
): DepartmentExposureDatum[] {
  const grouped = new Map<string, DepartmentExposureDatum>();
  cars.forEach((car) => {
    const key = departmentLabel(car);
    const current = grouped.get(key) || { department: key, open: 0, overdue: 0, total: 0 };
    current.total += 1;
    if (isOpen(car)) current.open += 1;
    if (isOverdue(car, today)) current.overdue += 1;
    grouped.set(key, current);
  });
  return [...grouped.values()]
    .sort((left, right) => right.overdue - left.overdue || right.open - left.open || left.department.localeCompare(right.department))
    .slice(0, limit);
}

export function isObservationFinding(row: QMSAuditRegisterRowOut): boolean {
  const type = String(row.finding.finding_type || "").toUpperCase();
  const level = String(row.finding.level || "").toUpperCase();
  return type === "OBSERVATION" || level.includes("LEVEL_4");
}

export function buildFindingConversionData(rows: QMSAuditRegisterRowOut[]): FindingConversionDatum[] {
  let observations = 0;
  let ncWithCar = 0;
  let ncWithoutCar = 0;
  rows.forEach((row) => {
    if (isObservationFinding(row)) {
      observations += 1;
      return;
    }
    if (row.linked_cars.length > 0) ncWithCar += 1;
    else ncWithoutCar += 1;
  });
  return [
    { name: "Observations", value: observations, fill: "var(--assurance-observation, #059669)" },
    { name: "NC with CAR", value: ncWithCar, fill: "var(--accent-primary, #2563eb)" },
    { name: "NC without CAR", value: ncWithoutCar, fill: "var(--accent-danger, #dc2626)" },
  ];
}

function daysBetween(from: string, to: string): number {
  const start = Date.parse(`${from}T00:00:00Z`);
  const end = Date.parse(`${to}T00:00:00Z`);
  if (Number.isNaN(start) || Number.isNaN(end)) return 0;
  return Math.max(0, Math.floor((end - start) / 86_400_000));
}

export function buildOverdueAgingData(cars: CAROut[], today: string): OverdueAgingDatum[] {
  const buckets: OverdueAgingDatum[] = [
    { bucket: "1–7d", count: 0 },
    { bucket: "8–30d", count: 0 },
    { bucket: "31–90d", count: 0 },
    { bucket: ">90d", count: 0 },
  ];
  cars.forEach((car) => {
    if (!isOverdue(car, today)) return;
    const due = agreedDue(car);
    if (!due) return;
    const age = daysBetween(due, today);
    if (age <= 7) buckets[0].count += 1;
    else if (age <= 30) buckets[1].count += 1;
    else if (age <= 90) buckets[2].count += 1;
    else buckets[3].count += 1;
  });
  return buckets;
}

export function buildClosureForecast(
  cars: CAROut[],
  onTimePercent: number | null,
): ClosureForecast {
  const openCount = cars.filter(isOpen).length;
  if (onTimePercent == null) {
    return {
      openCount,
      historicalOnTimeRate: null,
      expectedOnTimeClosures: null,
      methodology:
        "Insufficient measurable closed CARs to project. Need closed records with both agreed due and closure dates.",
    };
  }
  const rate = onTimePercent / 100;
  return {
    openCount,
    historicalOnTimeRate: Number(onTimePercent.toFixed(1)),
    expectedOnTimeClosures: Math.round(openCount * rate),
    methodology:
      `Projected on-time closures = open CARs × historical on-time rate (${onTimePercent.toFixed(1)}%). This is an empirical projection, not a Monte Carlo simulation.`,
  };
}
