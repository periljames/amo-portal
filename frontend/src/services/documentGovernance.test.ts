import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./auth", () => ({ authHeaders: () => ({ Authorization: "Bearer test" }) }));
vi.mock("./config", () => ({ getApiBaseUrl: () => "" }));

import {
  decideResponsibility,
  getDocumentGovernance,
  listGovernanceDocuments,
} from "./documentGovernance";

function response(payload: unknown): Response {
  return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
}

describe("document governance API client", () => {
  afterEach(() => vi.restoreAllMocks());

  it("keeps bounded library state in URL query parameters", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ items: [], pagination: { page: 2, per_page: 50, total: 0, returned: 0 } }));
    await listGovernanceDocuments("safarilink", { page: 2, per_page: 50, unresolved_ownership: true, unresolved_relationships: false });
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/doc-control/workspace/t/safarilink/governance/library?");
    expect(String(url)).toContain("page=2");
    expect(String(url)).toContain("per_page=50");
    expect(String(url)).toContain("unresolved_ownership=true");
    expect(String(url)).not.toContain("unresolved_relationships");
  });

  it("loads the normalized detail aggregate rather than the legacy profile endpoint", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response({}));
    await getDocumentGovernance("tenant", "manual-1");
    expect(String(fetchMock.mock.calls[0][0])).toContain("/documents/manual-1/governance");
  });

  it("posts an explicit human decision for detected responsibility", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ id: "assignment-1" }));
    await decideResponsibility("tenant", "assignment-1", "CONFIRMED", "Verified against the approval page.");
    const [, init] = fetchMock.mock.calls[0];
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({ decision: "CONFIRMED", comments: "Verified against the approval page." });
  });
});
