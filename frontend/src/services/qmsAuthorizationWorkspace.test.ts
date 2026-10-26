import { beforeEach, expect, it, vi } from "vitest";
vi.mock("./qmsPeople", () => ({ getQmsAuthorizationOverview: vi.fn(), listQmsAuthorizationPeople: vi.fn(), listQmsAuthorizationCases: vi.fn(), listQmsAuthorizationReviews: vi.fn(), listQmsAuthorizations: vi.fn(), listQmsPrivilegeRules: vi.fn() }));
import * as api from "./qmsPeople";
import { loadQmsAuthorizationWorkspace } from "./qmsAuthorizationWorkspace";

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getQmsAuthorizationOverview).mockResolvedValue({ permissions: { can_prepare: true }, metrics: {}, attention: [] } as never);
  for (const fn of [api.listQmsAuthorizationPeople, api.listQmsAuthorizationCases]) vi.mocked(fn).mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0, has_more: false } as never);
  for (const fn of [api.listQmsAuthorizationReviews, api.listQmsAuthorizations, api.listQmsPrivilegeRules]) vi.mocked(fn).mockResolvedValue({ items: [] } as never);
});
it("keeps people and cases available when another section fails", async () => {
  vi.mocked(api.listQmsAuthorizationPeople).mockResolvedValue({ items: [{ key: "james", name: "James" }], total: 1, limit: 100, offset: 0, has_more: false } as never);
  vi.mocked(api.listQmsAuthorizationReviews).mockRejectedValue(new Error("Review source unavailable"));
  const result = await loadQmsAuthorizationWorkspace("test", new AbortController().signal);
  expect(result.people[0].name).toBe("James");
  expect(result.errors).toEqual(["Reviews: Review source unavailable"]);
  expect(result.overview).toBeDefined();
});
it("does not request restricted policy for a self-service user", async () => {
  vi.mocked(api.getQmsAuthorizationOverview).mockResolvedValue({ permissions: { can_prepare: false, can_manage_policy: false }, metrics: {}, attention: [] } as never);
  await loadQmsAuthorizationWorkspace("test", new AbortController().signal);
  expect(api.listQmsPrivilegeRules).not.toHaveBeenCalled();
});
it("does not turn an unavailable permission overview into a privileged workspace", async () => {
  vi.mocked(api.getQmsAuthorizationOverview).mockRejectedValue(new Error("Denied"));
  await expect(loadQmsAuthorizationWorkspace("test", new AbortController().signal)).rejects.toThrow("Denied");
  expect(api.listQmsAuthorizationPeople).not.toHaveBeenCalled();
});
