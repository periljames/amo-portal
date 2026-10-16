import { expect, test, type Page } from "@playwright/test";
import { OFFLINE_CREATE_ROUTES } from "../../src/services/offlineCreateRoutes";

// The actual browser storage/crypto/HTTP modules run here. API outcomes are
// deterministic fixtures; this suite does not claim live database acceptance.
async function harness(page: Page) {
  await page.route("**/__offline_harness__", (route) => route.fulfill({ contentType: "text/html", body: "<html><body>Offline storage test</body></html>" }));
  await page.goto("/__offline_harness__");
  await page.evaluate(async () => {
    localStorage.setItem("amo_current_user", JSON.stringify({ id: "user-one", amo_id: "amo-one" }));
    sessionStorage.setItem("amo_portal_token", "test-token");
    const config = await import("/src/services/config.ts");
    config.setApiBaseRuntime(location.origin);
    const connectivity = await import("/src/services/portalConnectivity.ts");
    connectivity.notePortalResponse(new Response("{}", { status: 200 }));
    await import("/src/services/offlineHttp.ts");
    await import("/src/services/offlinePersistence.ts");
  });
}

const fieldwork = {
  client_mutation_id: "fieldwork-test-mutation-123456", device_id: "device-test-123456",
  device_sequence: 1, base_version: 0, client_timestamp: "2026-10-16T12:00:00Z",
  operation: "CHECKLIST_UPDATE", canonical_response_status: "COMPLIANT", reason: "Captured offline",
};
const commands = [
  { name: "QMS checklist", path: "/api/maintenance/amo/quality/audits/a/checklist-items/i/fieldwork-mutations", method: "POST", body: fieldwork },
  { name: "QMS finding", path: "/api/maintenance/amo/quality/audits/a/checklist-items/i/fieldwork-findings", method: "POST", body: { ...fieldwork, operation: "CREATE_FINDING", canonical_response_status: "NONCOMPLIANT", level: "LEVEL_2", severity: "MAJOR", description: "Recorded non-conformity" } },
  { name: "Roster create", path: "/rostering/versions/v/assignments", method: "POST", body: { source_reference_id: "device-assignment-123456" } },
  { name: "Roster edit", path: "/rostering/assignments/i", method: "PATCH", body: { expected_state_revision: 1 } },
  { name: "Maintenance task", path: "/work-orders/tasks/1", method: "PUT", body: { last_known_updated_at: "2026-10-16T12:00:00Z" } },
  { name: "Attendance", path: "/workforce/attendance-events", method: "POST", body: { idempotency_key: "device-attendance-123456" } },
];

const creationCommands = OFFLINE_CREATE_ROUTES.map((route) => ({
  name: route.id, path: route.path.replace(/\{[^}]+\}/g, "test-id"),
  method: "POST", body: { title: "Captured offline" }, autoQueue: true,
}));
for (const command of [...commands.map((command) => ({ ...command, autoQueue: false })), ...creationCommands]) {
  test(`${command.name} survives offline reload and replays the same command`, async ({ page, context }) => {
    await harness(page);
    await context.setOffline(true);
    const queued = await page.evaluate(async (command) => {
      const { portalFetch } = await import("/src/services/offlineHttp.ts");
      try {
        await portalFetch(command.path, { method: command.method, body: JSON.stringify(command.body),
          ...(command.autoQueue ? {} : { offline: { queueMutation: true } }) });
        throw new Error("Expected a device save");
      } catch (error) {
        if (error.name !== "OfflineQueuedError") throw error;
        return { id: error.operation.id, key: error.operation.idempotencyKey, body: error.operation.body };
      }
    }, command);
    await page.reload();
    const stored = await page.evaluate(async () => {
      const db = await new Promise<IDBDatabase>((resolve, reject) => {
        const request = indexedDB.open("amo-portal-offline", 3);
        request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
      });
      const rows = await new Promise<any[]>((resolve) => {
        const request = db.transaction("outbox").objectStore("outbox").getAll();
        request.onsuccess = () => resolve(request.result);
      });
      db.close();
      return rows.map((row) => ({ id: row.id, body: row.body, encrypted: Boolean(row.encryptedBody) }));
    });
    expect(stored).toEqual([{ id: queued.id, encrypted: true }]);
    await context.setOffline(false);
    await harness(page);
    let sent = 0;
    await page.route(`**${command.path}`, (route) => {
      sent++;
      expect(route.request().headers()["idempotency-key"]).toBe(queued.key);
      if (command.autoQueue) expect(route.request().headers()["x-amo-offline-command"]).toBe("1");
      expect(route.request().postData()).toBe(queued.body);
      return route.fulfill({ contentType: "application/json", body: "{}" });
    });
    const summary = await page.evaluate(async () => (await import("/src/services/offlinePersistence.ts")).replayOfflineMutations());
    expect(summary.total).toBe(0);
    expect(sent).toBe(1);
  });
}

test("two tabs share one replay lease", async ({ page, context }) => {
  await harness(page);
  await page.evaluate(async () => {
    const storage = await import("/src/services/offlinePersistence.ts");
    await storage.enqueueOfflineMutation({ path: "/workforce/attendance-events", method: "POST", body: JSON.stringify({ idempotency_key: "tab-test-123456" }) });
  });
  const other = await context.newPage();
  await harness(other);
  let release!: () => void;
  const held = new Promise<void>((resolve) => { release = resolve; });
  let requests = 0;
  await context.route("**/workforce/attendance-events", async (route) => {
    requests++;
    await held;
    await route.fulfill({ contentType: "application/json", body: "{}" });
  });
  const first = page.evaluate(async () => (await import("/src/services/offlinePersistence.ts")).replayOfflineMutations());
  await expect.poll(() => requests, { timeout: 10_000 }).toBe(1);
  const second = await other.evaluate(async () => (await import("/src/services/offlinePersistence.ts")).replayOfflineMutations());
  expect(second.total).toBe(1);
  expect(requests).toBe(1);
  release();
  expect((await first).total).toBe(0);
});

for (const path of ["/training/courses", "/tasks/my", "/aircraft", "/work-orders/", "/records/watchlists",
  "/inventory/stock", "/finance/invoices", "/api/maintenance/amo/procurement/suppliers", "/reliability/events"]) {
  test(`${path} cache survives reload and remains readable offline`, async ({ page, context }) => {
    await harness(page);
    await page.route(`**${path}`, (route) => route.fulfill({ contentType: "application/json", body: '[{"id":"saved-record"}]' }));
    await page.evaluate(async (path) => {
      const { portalFetch } = await import("/src/services/offlineHttp.ts");
      await portalFetch(path, { offline: { cacheTtlMs: 0 } });
    }, path);
    // Vite serves test code; production asset availability has separate service
    // worker coverage. Reset the JS heap, load test code, then cut connectivity
    // before reading the persisted data.
    await harness(page);
    await context.setOffline(true);
    const cached = await page.evaluate(async (path) => {
      const { portalFetch } = await import("/src/services/offlineHttp.ts");
      const response = await portalFetch(path);
      return { body: await response.json(), source: response.headers.get("X-AMO-Portal-Cache") };
    }, path);
    expect(cached).toEqual({ body: [{ id: "saved-record" }], source: "offline" });
  });
}

test("separate devices retain their drafts and require review of a conflicting revision", async ({ browser }) => {
  const devices = [await browser.newContext(), await browser.newContext()];
  try {
    const pages = await Promise.all(devices.map((device) => device.newPage()));
    let revision = 1;
    let savedNote = "";
    const committedKeys: string[] = [];
    for (const device of devices) {
      await device.route("**/rostering/assignments/device-test", async (route) => {
        const payload = route.request().postDataJSON();
        if (payload.expected_state_revision !== revision) {
          await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ detail: {
            error_code: "ROSTER_ASSIGNMENT_REVISION_CONFLICT", detail: "Another device updated this assignment.",
            conflicts: [{ current_state_revision: revision }], retryable: true,
          } }) });
          return;
        }
        revision++;
        savedNote = payload.note;
        committedKeys.push(route.request().headers()["idempotency-key"]);
        await route.fulfill({ contentType: "application/json", body: JSON.stringify({ state_revision: revision }) });
      });
    }
    for (const [index, page] of pages.entries()) {
      await harness(page);
      await devices[index].setOffline(true);
      await page.evaluate(async (note) => {
        const storage = await import("/src/services/offlinePersistence.ts");
        await storage.enqueueOfflineMutation({ path: "/rostering/assignments/device-test", method: "PATCH", entityType: "roster-assignment",
          body: JSON.stringify({ expected_state_revision: 1, note }) });
      }, `Device ${index + 1} edit`);
    }
    await devices[0].setOffline(false);
    expect((await pages[0].evaluate(async () => (await import("/src/services/offlinePersistence.ts")).replayOfflineMutations())).total).toBe(0);
    expect(savedNote).toBe("Device 1 edit");
    expect(await pages[1].evaluate(async () => (await import("/src/services/offlinePersistence.ts")).listOfflineMutations().then((rows) => rows.length))).toBe(1);
    await devices[1].setOffline(false);
    expect((await pages[1].evaluate(async () => (await import("/src/services/offlinePersistence.ts")).replayOfflineMutations())).conflict).toBe(1);
    expect(savedNote).toBe("Device 1 edit");
    const keys = await pages[1].evaluate(async () => {
      const storage = await import("/src/services/offlinePersistence.ts");
      const [conflict] = await storage.listOfflineMutations();
      const retried = await storage.retryOfflineMutation(conflict.id);
      return { original: conflict.idempotencyKey, reviewed: retried.idempotencyKey, total: (await storage.replayOfflineMutations()).total };
    });
    expect(keys.reviewed).not.toBe(keys.original);
    expect(keys.total).toBe(0);
    expect(savedNote).toBe("Device 2 edit");
    expect(committedKeys).toHaveLength(2);
  } finally {
    await Promise.all(devices.map((device) => device.close()));
  }
});
