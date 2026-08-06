import { beforeEach, describe, expect, it, vi } from "vitest";

const { getTokenMock, handleAuthFailureMock, portalFetchMock } = vi.hoisted(() => ({
  getTokenMock: vi.fn(),
  handleAuthFailureMock: vi.fn(),
  portalFetchMock: vi.fn(),
}));

vi.mock("./auth", () => ({
  getToken: getTokenMock,
  handleAuthFailure: handleAuthFailureMock,
}));

vi.mock("./offlineHttp", () => ({
  portalFetch: portalFetchMock,
}));

import {
  createDailyUtilisationDraft,
  getDailyUtilisationContext,
  postDailyUtilisation,
  previewDailyUtilisation,
  type DailyUtilisationPayload,
} from "./dailyUtilisation";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const payload: DailyUtilisationPayload = {
  operation_date: "2026-08-06",
  techlog_no: "TL-000123",
  station: "HKJK",
  flight_hours: "1.75",
  cycles: 2,
  nil_operation: false,
  source_reference: "TECHLOG-TL-000123",
  remarks: "Acceptance flight",
  idempotency_key: "daily-5Y-SLS-2026-08-06",
  component_overrides: [
    {
      component_id: 41,
      hours_delta: "1.25",
      cycles_delta: 1,
      reason: "Engine ground run excluded",
    },
  ],
};

describe("daily utilisation service contract", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getTokenMock.mockReturnValue("architecture-token");
  });

  it("loads the tenant-authorised aircraft context through the canonical route", async () => {
    portalFetchMock.mockResolvedValue(jsonResponse({ aircraft_serial_number: "AC 123/α" }));

    await getDailyUtilisationContext("AC 123/α");

    expect(portalFetchMock).toHaveBeenCalledTimes(1);
    const [path, options] = portalFetchMock.mock.calls[0] as [string, RequestInit & { offline: unknown }];
    expect(path).toBe(
      `/architecture/daily-utilisation/aircraft/${encodeURIComponent("AC 123/α")}/context`,
    );
    expect(options.method).toBe("GET");
    expect(options.credentials).toBe("include");
    expect(options.offline).toEqual({ cache: true, queueMutation: false });
    expect((options.headers as Headers).get("Authorization")).toBe("Bearer architecture-token");
  });

  it("preserves exact decimal strings and disables offline mutation queuing", async () => {
    portalFetchMock.mockResolvedValue(jsonResponse({ can_post: true, blockers: [], exposures: [] }));

    await previewDailyUtilisation("5Y-SLS", payload);

    const [path, options] = portalFetchMock.mock.calls[0] as [string, RequestInit & { offline: unknown }];
    expect(path).toBe("/architecture/daily-utilisation/aircraft/5Y-SLS/preview");
    expect(options.method).toBe("POST");
    expect(options.offline).toEqual({ cache: false, queueMutation: false });
    expect(JSON.parse(String(options.body))).toEqual(payload);
    expect(JSON.parse(String(options.body)).flight_hours).toBe("1.75");
    expect(JSON.parse(String(options.body)).component_overrides[0].hours_delta).toBe("1.25");
  });

  it("uses the controlled draft and post endpoints", async () => {
    portalFetchMock
      .mockResolvedValueOnce(jsonResponse({ entry: { id: "entry-7" }, preview: {} }))
      .mockResolvedValueOnce(jsonResponse({ entry: { id: "entry-7" }, component_updates: 1 }));

    await createDailyUtilisationDraft("5Y-SLS", payload);
    await postDailyUtilisation("entry 7/approved");

    expect(portalFetchMock.mock.calls[0][0]).toBe(
      "/architecture/daily-utilisation/aircraft/5Y-SLS/entries",
    );
    expect(portalFetchMock.mock.calls[1][0]).toBe(
      `/architecture/daily-utilisation/entries/${encodeURIComponent("entry 7/approved")}/post`,
    );
  });

  it("invalidates an expired session on an unauthorised response", async () => {
    portalFetchMock.mockResolvedValue(jsonResponse({ detail: "expired" }, 401));

    await expect(getDailyUtilisationContext("5Y-SLS")).rejects.toThrow(
      "Session expired. Please sign in again.",
    );
    expect(handleAuthFailureMock).toHaveBeenCalledWith("expired");
  });
});
