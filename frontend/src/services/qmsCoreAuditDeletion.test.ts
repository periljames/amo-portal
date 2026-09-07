import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { authFailure, beginLoading, endLoading } = vi.hoisted(() => ({
  authFailure: vi.fn(),
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
  beginBackgroundLoading: vi.fn(),
  endBackgroundLoading: vi.fn(),
  beginLoading,
  endLoading,
}));

import {
  qmsDeleteAudit,
  qmsPurgeAudit,
  qmsRestoreAudit,
} from "./qmsCore";

describe("QMS audit deletion", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal("window", {
      setTimeout: globalThis.setTimeout.bind(globalThis),
      clearTimeout: globalThis.clearTimeout.bind(globalThis),
    });
    authFailure.mockReset();
    beginLoading.mockReset();
    endLoading.mockReset();
  });

  afterEach(() => vi.unstubAllGlobals());

  it("keeps the handled modal failure out of the global toast bridge and parses its safe message", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        detail: {
          code: "AUDIT_DELETE_FAILED",
          message: "The audit could not be deleted. No database records were changed.",
        },
      }), {
        status: 500,
        headers: { "content-type": "application/json" },
      }),
    );

    await expect(qmsDeleteAudit("audit/1"))
      .rejects.toThrow("The audit could not be deleted. No database records were changed.");

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/quality/audits/audit%2F1",
      expect.objectContaining({
        method: "DELETE",
        headers: expect.objectContaining({
          Authorization: "Bearer quality-token",
          "X-AMO-Silent-Error": "1",
        }),
      }),
    );
    expect(beginLoading).toHaveBeenCalledOnce();
    expect(endLoading).toHaveBeenCalledOnce();
  });

  it("moves an audit to the recycle bin with an optional encoded reason", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        deleted: true,
        recoverable: true,
        purge_at: "2026-10-05T10:30:00Z",
      }), { status: 200, headers: { "content-type": "application/json" } }),
    );

    await expect(qmsDeleteAudit("audit/1", "Duplicate programme entry"))
      .resolves.toMatchObject({ deleted: true, recoverable: true });

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/quality/audits/audit%2F1?reason=Duplicate+programme+entry",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("keeps restore and irreversible purge as distinct backend operations", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "audit-1" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));

    await qmsRestoreAudit("audit-1");
    await qmsPurgeAudit("audit-1");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "https://api.example.test/quality/audits/audit-1/restore",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "https://api.example.test/quality/audits/audit-1/purge",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
