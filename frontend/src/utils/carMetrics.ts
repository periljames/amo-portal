import type { CAROut, CARStatus } from "../services/qms";

const CLOSED_STATUSES: CARStatus[] = ["CLOSED", "CANCELLED"];

export const isCarClosedStatus = (status: CARStatus): boolean => CLOSED_STATUSES.includes(status);

export const isCarOverdue = (car: CAROut, today: string): boolean => {
  if (!car.due_date) return false;
  if (isCarClosedStatus(car.status)) return false;
  return car.due_date < today;
};

export const deriveCarMetrics = (cars: CAROut[], now: Date = new Date()) => {
  const today = now.toISOString().slice(0, 10);
  const total = cars.length;
  const open = cars.filter((car) => !isCarClosedStatus(car.status)).length;
  const overdue = cars.filter((car) => isCarOverdue(car, today)).length;
  const inReview = cars.filter((car) => car.status === "PENDING_VERIFICATION").length;
  return { total, open, overdue, inReview, today };
};
