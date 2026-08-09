import { beforeEach, describe, expect, it, vi } from "vitest";

import { getToken } from "./auth";
import { emitProductEvent, trackProductWorkflow } from "./productAnalytics";

vi.mock("./auth", () => ({
  getToken: vi.fn(),
}));

const getTokenMock = vi.mocked(getToken);

function response(ok = true): Response {
  return { ok } as Response;
}

describe("product analytics", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    getTokenMock.mockReset();
    getTokenMock.mockReturnValue("test-token");
  });

  it("does not emit without an authenticated token", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    getTokenMock.mockReturnValue(null);

    const emitted = await emitProductEvent({
      event_type: "workflow_completed",
      module: "quality",
      metadata: { workflow: "audit-closeout" },
    });

    expect(emitted).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("drops identifiers and payload data from event metadata", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(true));
    vi.stubGlobal("fetch", fetchMock);

    const emitted = await emitProductEvent({
      event_type: "workflow_completed",
      module: "Document Control / Reader",
      outcome: "SUCCESS",
      duration_ms: 123.6,
      metadata: {
        workflow: "document-metadata-update",
        source: "document-control",
        feature: "governance",
        route_name: "documents",
        tenant_id: "tenant-secret",
        user_id: "user-secret",
        document_id: "document-secret",
        notes: "free text must not leave the workflow",
        nested: { secret: true },
      },
    });

    expect(emitted).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(init.body));
    expect(body.module).toBe("document-control-reader");
    expect(body.duration_ms).toBe(124);
    expect(body.metadata).toEqual({
      workflow: "document-metadata-update",
      source: "document-control",
      feature: "governance",
      route_name: "documents",
    });
    expect(JSON.stringify(body)).not.toContain("tenant-secret");
    expect(JSON.stringify(body)).not.toContain("user-secret");
    expect(JSON.stringify(body)).not.toContain("document-secret");
    expect(JSON.stringify(body)).not.toContain("free text");
  });

  it("is fail-open when the analytics endpoint is unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("analytics unavailable")));

    await expect(emitProductEvent({
      event_type: "workflow_started",
      module: "work-orders",
      metadata: { workflow: "work-order-create" },
    })).resolves.toBe(false);
  });

  it("preserves a successful business result while emitting start and completion", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(true));
    vi.stubGlobal("fetch", fetchMock);

    const result = await trackProductWorkflow({
      module: "work-orders",
      workflow: "task-inspection",
      source: "maintenance",
      operation: async () => ({ accepted: true }),
    });

    expect(result).toEqual({ accepted: true });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const bodies = fetchMock.mock.calls.map(([, init]) => JSON.parse(String((init as RequestInit).body)));
    expect(bodies.map((body) => body.event_type)).toEqual(["workflow_started", "workflow_completed"]);
    expect(bodies[1].outcome).toBe("SUCCESS");
    expect(bodies[1].metadata).toEqual({ workflow: "task-inspection", source: "maintenance" });
  });

  it("preserves the original business exception while emitting failure", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(true));
    vi.stubGlobal("fetch", fetchMock);
    const businessError = new Error("authoritative operation failed");

    await expect(trackProductWorkflow({
      module: "quality",
      workflow: "audit-report-share",
      source: "qms-audit-hub",
      operation: async () => {
        throw businessError;
      },
    })).rejects.toBe(businessError);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const bodies = fetchMock.mock.calls.map(([, init]) => JSON.parse(String((init as RequestInit).body)));
    expect(bodies.map((body) => body.event_type)).toEqual(["workflow_started", "workflow_failed"]);
    expect(bodies[1].outcome).toBe("FAILED");
  });
});
