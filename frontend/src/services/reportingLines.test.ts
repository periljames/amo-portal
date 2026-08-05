import { beforeEach, describe, expect, it, vi } from "vitest";

const apiGetMock = vi.hoisted(() => vi.fn());
const apiPatchMock = vi.hoisted(() => vi.fn());
const apiPostMock = vi.hoisted(() => vi.fn());
const apiPutMock = vi.hoisted(() => vi.fn());
const authHeadersMock = vi.hoisted(() => vi.fn(() => ({ Authorization: "Bearer test" })));

vi.mock("./crs", () => ({
  apiGet: apiGetMock,
  apiPatch: apiPatchMock,
  apiPost: apiPostMock,
  apiPut: apiPutMock,
}));

vi.mock("./auth", () => ({
  authHeaders: authHeadersMock,
}));

import {
  clearMyTitlePreference,
  createGuidedAssignment,
  decideTitlePreference,
  endReportingAssignment,
  getReportingWorkspace,
  submitMyTitlePreference,
  transferReportingAssignment,
  updateReportingAssignment,
  type GuidedAssignmentInput,
  type ReportingAssignmentTransferInput,
} from "./reportingLines";

const managerAssignment: GuidedAssignmentInput = {
  user_id: "user-1",
  position_id: "position-1",
  reporting_manager_user_id: "manager-1",
  assignment_type: "SUBSTANTIVE",
  is_primary: true,
  effective_from: "2026-08-05",
  effective_to: null,
  fte_percent: "100",
  matrix_reporting: false,
  matrix_reason: null,
  display_title: "Engineer",
};

const transfer: ReportingAssignmentTransferInput = {
  target_position_id: "position-2",
  effective_from: "2026-08-10",
  reporting_manager_user_id: "manager-2",
  assignment_type: "SUBSTANTIVE",
  fte_percent: "100",
  matrix_reporting: false,
  matrix_reason: null,
  display_title: "Senior Engineer",
  reason: "Approved department transfer",
};

describe("reporting-line API contracts", () => {
  beforeEach(() => {
    apiGetMock.mockReset();
    apiPatchMock.mockReset();
    apiPostMock.mockReset();
    apiPutMock.mockReset();
    authHeadersMock.mockClear();
  });

  it("loads the tenant-scoped reporting workspace", async () => {
    await getReportingWorkspace();

    expect(apiGetMock).toHaveBeenCalledWith(
      "/auth/organization/reporting/workspace",
      { headers: { Authorization: "Bearer test" } },
    );
  });

  it("uses the manager lifecycle surface for manager mutations", async () => {
    await createGuidedAssignment("MANAGER", managerAssignment);
    await updateReportingAssignment("MANAGER", "assignment / 1", {
      display_title: "Chief Crew",
    });
    await endReportingAssignment(
      "MANAGER",
      "assignment / 1",
      "2026-08-09",
      "  Contract completed  ",
    );
    await transferReportingAssignment("MANAGER", "assignment / 1", transfer);

    expect(apiPostMock).toHaveBeenNthCalledWith(
      1,
      "/auth/organization/reporting/manager/assignments",
      managerAssignment,
      { headers: { Authorization: "Bearer test" } },
    );
    expect(apiPatchMock).toHaveBeenCalledWith(
      "/auth/organization/reporting/manager/assignments/assignment%20%2F%201",
      { display_title: "Chief Crew" },
      { headers: { Authorization: "Bearer test" } },
    );
    expect(apiPostMock).toHaveBeenNthCalledWith(
      2,
      "/auth/organization/reporting/manager/assignments/assignment%20%2F%201/end",
      { end_on: "2026-08-09", reason: "Contract completed" },
      { headers: { Authorization: "Bearer test" } },
    );
    expect(apiPostMock).toHaveBeenNthCalledWith(
      3,
      "/auth/organization/reporting/manager/assignments/assignment%20%2F%201/transfer",
      transfer,
      { headers: { Authorization: "Bearer test" } },
    );
  });

  it("uses the elevated admin lifecycle surface for admin decisions", async () => {
    await decideTitlePreference(
      "ADMIN",
      "preference / 1",
      "APPROVE",
      "  Matches approved working arrangement  ",
    );

    expect(apiPostMock).toHaveBeenCalledWith(
      "/accounts/admin/organization/reporting/title-preferences/preference%20%2F%201/decision",
      {
        decision: "APPROVE",
        note: "Matches approved working arrangement",
      },
      { headers: { Authorization: "Bearer test" } },
    );
  });

  it("normalizes self-service title requests and reset calls", async () => {
    await submitMyTitlePreference("  Chief Crew  ", "  Operational working title  ");
    await clearMyTitlePreference();

    expect(apiPutMock).toHaveBeenCalledWith(
      "/auth/organization/reporting/my-title",
      {
        requested_title: "Chief Crew",
        reason: "Operational working title",
      },
      { headers: { Authorization: "Bearer test" } },
    );
    expect(apiPostMock).toHaveBeenCalledWith(
      "/auth/organization/reporting/my-title/clear",
      {},
      { headers: { Authorization: "Bearer test" } },
    );
  });
});
