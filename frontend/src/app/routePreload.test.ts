import { afterEach, beforeEach, expect, it, vi } from "vitest";

const loaders = vi.hoisted(() => ({
  overview: vi.fn().mockResolvedValue({}),
  people: vi.fn().mockResolvedValue({}),
  missions: vi.fn().mockResolvedValue({}),
}));
vi.mock("./qmsRouteLoaders", () => ({
  qmsPageLoaders: loaders,
  qmsRouteLoaderKey: (path: string) => path.includes("workspace=people") ? "people"
    : path.includes("workspace=missions") ? "missions" : "overview",
}));

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  vi.useFakeTimers();
  vi.stubGlobal("window", Object.assign(new EventTarget(), {
    location: { origin: "https://portal.test" }, setTimeout, clearTimeout,
  }));
  vi.stubGlobal("document", Object.assign(new EventTarget(), { visibilityState: "visible" }));
  vi.stubGlobal("navigator", { onLine: true });
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

it("preserves workspace query state and coalesces repeated intent events", async () => {
  const { preloadRoute } = await import("./routePreload");
  await Promise.all(Array.from({ length: 20 }, () => preloadRoute("/maintenance/t/quality?workspace=people")));
  expect(loaders.people).toHaveBeenCalledTimes(1);
  expect(loaders.overview).toHaveBeenCalledTimes(1);
  expect(loaders.missions).not.toHaveBeenCalled();
});

it("starts only one idle route at a time and cancels remaining work", async () => {
  let finish!: (value: object) => void;
  loaders.people.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
  const { scheduleWorkspaceRoutePreload } = await import("./routePreload");
  const cancel = scheduleWorkspaceRoutePreload([
    "/maintenance/t/quality?workspace=people", "/maintenance/t/quality?workspace=missions",
  ]);
  await vi.advanceTimersByTimeAsync(1200);
  expect(loaders.people).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(10_000);
  expect(loaders.missions).not.toHaveBeenCalled();
  cancel();
  finish({});
  await vi.advanceTimersByTimeAsync(3000);
  expect(loaders.missions).not.toHaveBeenCalled();
});

it("does not start background work offline or on a data-saving connection", async () => {
  const { scheduleWorkspaceRoutePreload } = await import("./routePreload");
  vi.stubGlobal("navigator", { onLine: false });
  scheduleWorkspaceRoutePreload(["/maintenance/t/quality?workspace=people"]);
  await vi.advanceTimersByTimeAsync(10_000);
  vi.stubGlobal("navigator", { onLine: true, connection: { saveData: true } });
  scheduleWorkspaceRoutePreload(["/maintenance/t/quality?workspace=people"]);
  await vi.advanceTimersByTimeAsync(10_000);
  expect(loaders.people).not.toHaveBeenCalled();
});
