import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const {
  authFailure,
  beginBackgroundLoading,
  endBackgroundLoading,
  beginLoading,
  endLoading,
} = vi.hoisted(() => ({
  authFailure: vi.fn(),
  beginBackgroundLoading: vi.fn(),
  endBackgroundLoading: vi.fn(),
  beginLoading: vi.fn(),
  endLoading: vi.fn(),
}));

vi.mock("./auth", () => ({
  getToken: () => "quality-token",
  handleAuthFailure: authFailure,
}));

vi.mock("./config", () => ({
  getApiBaseUrl: () => "https://api.example.test",
}));

vi.mock("./loading", () => ({
  beginBackgroundLoading,
  endBackgroundLoading,
  beginLoading,
  endLoading,
}));

import {
  qmsAddCarAction,
  qmsListCarActions,
  qmsShareAuditReport,
} from "./qmsAuditHubActions";

describe("Quality audit hub API helpers", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    authFailure.mockReset();
    beginBackgroundLoading.mockReset();
    endBackgroundLoading.mockReset();
    beginLoading.mockReset();
    endLoading.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("scopes CAR action reads to the requested CAR and closes background loading", async () => {
    const payload = [{
      id: "action-1",
      car_id: "car/with spaces",
      action_type: "COMMENT",
      message: "Reviewed",
      actor_user_id: null,
      created_at: "2026-07-22T10:00:00Z",
    }];
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await expect(qmsListCarActions("car/with spaces")).resolves.toEqual(payload);
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/quality/cars/car%2Fwith%20spaces/actions",
      expect.objectContaining({
        method: "GET",
        credentials: "include",
        headers: expect.objectContaining({ Authorization: "Bearer quality-token" }),
      }),
    );
    expect(beginBackgroundLoading).toHaveBeenCalledOnce();
    expect(endBackgroundLoading).toHaveBeenCalledOnce();
  });

  it("posts a normalized CAR action and always closes foreground loading", async () => {
    const response = {
      id: "action-2",
      car_id: "car-2",
      action_type: "COMMENT",
      message: "Evidence checked",
      actor_user_id: "user-1",
      created_at: "2026-07-22T10:00:00Z",
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(response), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await expect(qmsAddCarAction("car-2", { message: "Evidence checked" })).resolves.toEqual(response);
    const [, init] = fetchMock.mock.calls[0];
    expect(init).toEqual(expect.objectContaining({ method: "POST" }));
    expect(JSON.parse(String(init?.body))).toEqual({
      action_type: "COMMENT",
      message: "Evidence checked",
    });
    expect(beginLoading).toHaveBeenCalledOnce();
    expect(endLoading).toHaveBeenCalledOnce();
  });

  it("surfaces backend validation detail instead of an opaque status string", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "At least one recipient group is required." }), {
        status: 422,
        headers: { "content-type": "application/json" },
      }),
    );

    await expect(qmsShareAuditReport("audit-1", { recipient_groups: [] }))
      .rejects.toThrow("At least one recipient group is required.");
    expect(endLoading).toHaveBeenCalledOnce();
  });

  it("invalidates the session on 401 while preserving loading cleanup", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 401 }));

    await expect(qmsListCarActions("car-3"))
      .rejects.toThrow("Session expired. Please sign in again.");
    expect(authFailure).toHaveBeenCalledWith("expired");
    expect(endBackgroundLoading).toHaveBeenCalledOnce();
  });

  it("returns a deterministic timeout error and clears foreground loading", async () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    }));

    const handledRequest = qmsAddCarAction("car-4", { message: "Ping" }).catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(45_000);

    await expect(handledRequest).resolves.toEqual(
      new Error("Quality API request timed out after 45 seconds."),
    );
    expect(endLoading).toHaveBeenCalledOnce();
  });
});

describe("Quality workflow integrity and public CAR UI contracts", () => {
  const enhancementsHostSource = readFileSync(
    new URL("../components/QMS/QualityEnhancementsHost.tsx", import.meta.url),
    "utf8",
  );
  const routeGateSource = readFileSync(
    new URL("../components/QMS/QualityEnhancementsRouteGate.tsx", import.meta.url),
    "utf8",
  );
  const mainSource = readFileSync(new URL("../main.tsx", import.meta.url), "utf8");
  const inviteCss = readFileSync(
    new URL("../styles/car-invite-responsive.css", import.meta.url),
    "utf8",
  );

  it("fails closed when the authoritative audit workflow is unavailable", () => {
    expect(enhancementsHostSource).toContain("data?.degraded === true");
    expect(enhancementsHostSource).toContain("Authoritative workflow unavailable");
    expect(enhancementsHostSource).toContain("It will not use locally invented completion values");
    expect(enhancementsHostSource).toContain("quality-workflow-is-degraded");
  });

  it("does not load PDF.js into unrelated portal workspaces", () => {
    expect(mainSource).toContain("QualityEnhancementsRouteGate");
    expect(mainSource).not.toContain("QualityChecklistPdfFormEditorHost");
    expect(routeGateSource).toContain('import("./QualityEnhancementsHost")');
    expect(routeGateSource).toContain("/car-invite");
    expect(routeGateSource).toContain("<ModalTopLayerGuard />");
    expect(routeGateSource).not.toContain("QualityChecklistPdfFormEditorHost");
    expect(enhancementsHostSource).not.toContain('activeTab={auditSessionStage === "prepare" ? "checklist" : null}');
    expect(enhancementsHostSource).toContain("<QualityChecklistTemplateHost amoCode={amoCode} auditKey={route?.auditKey} />");
  });

  it("keeps the public CAR workflow usable at normal browser zoom", () => {
    expect(inviteCss).toContain(".car-invite-stage:not(.is-active)");
    expect(inviteCss).toContain("max-height: none");
    expect(inviteCss).toContain(":has(.car-invite-badge--success)");
  });
});
