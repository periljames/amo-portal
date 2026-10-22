import { describe, expect, it } from "vitest";

import type { CAROut, QMSAuditRegisterRowOut } from "../../services/qms";
import { exposureToSeries } from "./qmsCarPerformanceChartView";
import {
  buildClosureForecast,
  buildFindingConversionData,
  buildQpiChartData,
  buildWorkloadChartData,
  QMS_CLOSURE_TARGET,
} from "./qmsCarPerformanceCharts";

function car(overrides: Partial<CAROut> = {}): CAROut {
  return {
    id: "car-1",
    car_number: "CAR-1",
    title: "Test",
    status: "OPEN",
    priority: "MEDIUM",
    ...overrides,
  } as CAROut;
}

function finding(overrides: Partial<QMSAuditRegisterRowOut> = {}): QMSAuditRegisterRowOut {
  return {
    finding: {
      id: "f-1",
      finding_type: "NON_CONFORMITY",
      level: "LEVEL_2",
    },
    linked_cars: [],
    ...overrides,
  } as QMSAuditRegisterRowOut;
}

describe("qmsCarPerformanceCharts", () => {
  it("builds QPI bars against the 80% target", () => {
    const data = buildQpiChartData(72.5);
    expect(data[0]).toMatchObject({ name: "On-time %", value: 72.5 });
    expect(data[1]).toMatchObject({ name: "Target", value: QMS_CLOSURE_TARGET });
  });

  it("builds workload and finding conversion series from live counts", () => {
    expect(buildWorkloadChartData({ open: 4, overdue: 2, review: 1, closed: 3 }).map((row) => row.value)).toEqual([1, 2, 1, 3]);
    const conversion = buildFindingConversionData([
      finding({ finding: { id: "1", finding_type: "OBSERVATION", level: "LEVEL_4" } as QMSAuditRegisterRowOut["finding"], linked_cars: [] }),
      finding({ linked_cars: [{ id: "c1" } as never] }),
      finding(),
    ]);
    expect(conversion.map((row) => row.value)).toEqual([1, 1, 1]);
  });

  it("projects expected on-time closures from the empirical rate", () => {
    const forecast = buildClosureForecast([car(), car({ id: "car-2", status: "CLOSED" })], 50);
    expect(forecast.openCount).toBe(1);
    expect(forecast.expectedOnTimeClosures).toBe(1);
    expect(forecast.methodology).toContain("empirical");
  });

  it("flattens department exposure for non-stacked chart kinds", () => {
    expect(exposureToSeries([
      { department: "Engineering", open: 2, overdue: 1, total: 4 },
      { department: "Quality", open: 3, overdue: 3, total: 3 },
    ]).map((row) => ({ name: row.name, value: row.value }))).toEqual([
      { name: "Engineering", value: 2 },
      { name: "Quality", value: 3 },
    ]);
  });
});

it("does not count an overdue review twice in workload totals", () => {
 const rows = buildWorkloadChartData({ open: 10, overdue: 4, review: 3, overdueReview: 2, closed: 5 });
 expect(rows.map(row => row.value)).toEqual([5, 2, 3, 5]);
 expect(rows.reduce((total,row)=>total+row.value,0)).toBe(15);
});
