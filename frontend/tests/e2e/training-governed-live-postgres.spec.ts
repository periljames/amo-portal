import { expect, test, type Page } from "@playwright/test";

const LIVE_ENABLED = process.env.E2E_LIVE_TRAINING_GOVERNANCE === "1";
const AMO_CODE = process.env.E2E_TRAINING_AMO_CODE || "trngate";
const ADMIN_EMAIL = process.env.E2E_TRAINING_ADMIN_EMAIL || "";
const ADMIN_PASSWORD = process.env.E2E_TRAINING_ADMIN_PASSWORD || "";
const USER_ID = "00000000-0000-4000-8100-000000000003";
const EVENT_ID = "00000000-0000-4000-8100-000000000005";
const COURSE_REVISION_ID = "00000000-0000-4000-8100-000000000009";
const MODULE_THEORY_ID = "00000000-0000-4000-8100-000000000010";
const MODULE_PRACTICAL_ID = "00000000-0000-4000-8100-000000000011";
const PRACTICAL_TASK_ID = "00000000-0000-4000-8100-000000000012";
const ASSESSOR_AUTH_ID = "00000000-0000-4000-8100-000000000015";
const QUESTION_REVISION_ID = "00000000-0000-4000-8100-000000000019";
const BLUEPRINT_ID = "00000000-0000-4000-8100-000000000020";

let materialErrors: string[] = [];

test.use({
  viewport: { width: 1440, height: 900 },
  ignoreHTTPSErrors: true,
  trace: "retain-on-failure",
  screenshot: "on",
});
test.setTimeout(120_000);

function watchMaterialErrors(page: Page): void {
  materialErrors = [];
  page.on("pageerror", (error) => materialErrors.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const text = message.text();
    if (/favicon\.ico/i.test(text)) return;
    materialErrors.push(`console: ${text}`);
  });
  page.on("response", (response) => {
    if (response.status() >= 500) materialErrors.push(`http ${response.status()}: ${response.url()}`);
  });
}

async function signIn(page: Page): Promise<void> {
  await page.goto(`/maintenance/${encodeURIComponent(AMO_CODE)}/login`);
  await page.getByLabel("Email").fill(ADMIN_EMAIL);
  const continueButton = page.getByRole("button", { name: "Continue", exact: true });
  if (await continueButton.count()) await continueButton.click();
  await page.locator("#password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign In", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/, { timeout: 30_000 });
}

async function api<T>(page: Page, path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  return page.evaluate(async ({ pathValue, initValue }) => {
    const token = sessionStorage.getItem("amo_portal_token");
    if (!token) throw new Error("Authenticated Training session token is unavailable");
    const response = await fetch(pathValue, {
      method: initValue?.method || "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        ...(initValue?.body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: initValue?.body === undefined ? undefined : JSON.stringify(initValue.body),
    });
    const text = await response.text();
    let payload: unknown = null;
    if (text) {
      try { payload = JSON.parse(text); } catch { payload = text; }
    }
    if (!response.ok) throw new Error(`${initValue?.method || "GET"} ${pathValue} failed: ${response.status} ${text}`);
    return payload as T;
  }, { pathValue: path, initValue: init || {} });
}

test.describe.serial("Training governed live PostgreSQL journey", () => {
  test.skip(!LIVE_ENABLED, "Set E2E_LIVE_TRAINING_GOVERNANCE=1 to run live governed Training acceptance.");

  test.beforeEach(async ({ page }) => {
    if (!ADMIN_EMAIL || !ADMIN_PASSWORD) throw new Error("Live Training credentials are required");
    watchMaterialErrors(page);
    await signIn(page);
  });

  test.afterEach(() => {
    expect(materialErrors, materialErrors.join("\n")).toEqual([]);
  });

  test("browser -> FastAPI -> PostgreSQL enforces readiness, practical, exam and completion governance", async ({ page }) => {
    const readiness = await api<{ status: string; blockers: unknown[]; applicable_rules?: unknown[] }>(
      page,
      `/training/operating/governance/events/${EVENT_ID}/readiness`,
    );
    expect(readiness.status).toBe("READY");
    expect(readiness.blockers).toEqual([]);

    const start = await api<{ status: string; readiness: { status: string } }>(
      page,
      `/training/operating/governance/events/${EVENT_ID}/start`,
      { method: "POST" },
    );
    expect(start.status).toBe("IN_PROGRESS");
    expect(start.readiness.status).toBe("READY");

    for (const moduleId of [MODULE_THEORY_ID, MODULE_PRACTICAL_ID]) {
      const attendance = await api<{ status: string; user_id: string }>(
        page,
        `/training/operating/governance/events/${EVENT_ID}/modules/${moduleId}/attendance`,
        { method: "PUT", body: { user_id: USER_ID, status: "COMPLETE", evidence_json: [{ type: "ci_browser" }] } },
      );
      expect(attendance.status).toBe("COMPLETE");
      expect(attendance.user_id).toBe(USER_ID);
    }

    const assessorReadiness = await api<{ eligible: boolean; reasons: string[] }>(
      page,
      `/training/operating/governance/technical-authorisations/${USER_ID}/readiness?privilege_type=ASSESSOR&on_date=${new Date().toISOString().slice(0, 10)}&course_id=${COURSE_REVISION_ID}&practical=true`,
    );
    expect(assessorReadiness).toMatchObject({ eligible: true, reasons: [] });

    const practical = await api<{ result: string; practical_task_id: string }>(
      page,
      `/training/operating/governance/events/${EVENT_ID}/practical/${PRACTICAL_TASK_ID}`,
      { method: "POST", body: { user_id: USER_ID, assessor_authorisation_id: ASSESSOR_AUTH_ID, result: "PASS", evidence_json: [{ type: "ci_browser" }] } },
    );
    expect(practical.result).toBe("PASS");
    expect(practical.practical_task_id).toBe(PRACTICAL_TASK_ID);

    const generation = await api<{ id: string; question_revision_ids: string[]; status: string }>(
      page,
      "/training/operating/governance/exams/generations",
      { method: "POST", body: { event_id: EVENT_ID, blueprint_id: BLUEPRINT_ID, generation_code: `CI-${Date.now()}`, security_metadata: { source: "live_browser_ci" } } },
    );
    expect(generation.status).toBe("ACTIVE");
    expect(generation.question_revision_ids).toEqual([QUESTION_REVISION_ID]);

    const attempt = await api<{ id: string; status: string }>(
      page,
      "/training/operating/governance/exams/attempts",
      { method: "POST", body: { generation_id: generation.id, event_id: EVENT_ID } },
    );
    expect(attempt.status).toBe("IN_PROGRESS");

    const learnerExam = await api<{ attempt_id: string; questions: Array<Record<string, unknown>> }>(
      page,
      `/training/operating/governance/exams/attempts/${attempt.id}/learner`,
    );
    expect(learnerExam.attempt_id).toBe(attempt.id);
    expect(learnerExam.questions).toHaveLength(1);
    expect(learnerExam.questions[0]).toMatchObject({ question_revision_id: QUESTION_REVISION_ID, options: ["A", "B"] });
    expect(learnerExam.questions[0]).not.toHaveProperty("answer_key_json");
    expect(learnerExam.questions[0]).not.toHaveProperty("explanation");

    const submitted = await api<{ status: string; result: string; score: string | number }>(
      page,
      `/training/operating/governance/exams/attempts/${attempt.id}/submit`,
      { method: "POST", body: { responses: { [QUESTION_REVISION_ID]: { selected_option: "A" } } } },
    );
    expect(submitted.status).toBe("GRADED");
    expect(submitted.result).toBe("PASS");
    expect(Number(submitted.score)).toBe(100);

    const completion = await api<{ status: string; certificate_eligible: boolean; blockers: string[] }>(
      page,
      "/training/operating/governance/completion/evaluate",
      {
        method: "POST",
        body: {
          required_module_ids: [MODULE_THEORY_ID, MODULE_PRACTICAL_ID],
          completed_module_ids: [MODULE_THEORY_ID, MODULE_PRACTICAL_ID],
          required_practical_task_ids: [PRACTICAL_TASK_ID],
          passed_practical_task_ids: [PRACTICAL_TASK_ID],
          required_assessments: [attempt.id],
          passed_assessments: [attempt.id],
          additional_blockers: [],
        },
      },
    );
    expect(completion).toEqual({ status: "READY_FOR_CERTIFICATE", certificate_eligible: true, blockers: [] });

    const batch = await api<{ ready_user_ids: string[]; blocked_count: number }>(
      page,
      "/training/operating/governance/completion/batch-certificate",
      { method: "POST", body: [{ user_id: USER_ID, ...completion }] },
    );
    expect(batch.ready_user_ids).toEqual([USER_ID]);
    expect(batch.blocked_count).toBe(0);
  });
});
