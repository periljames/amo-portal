import { mockQualityShell } from "./helpers/mockQualityShell";
import { expect, test, type Page, type Route } from "@playwright/test";

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function prepare(
  page: Page,
  qualityHandler: (route: Route, url: URL) => Promise<void>,
  role: "QUALITY_MANAGER" | "AUDITOR" = "QUALITY_MANAGER",
): Promise<void> {
  await mockQualityShell(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  const token = futureToken();
  await page.addInitScript(({ storedToken, storedRole }) => {
    sessionStorage.setItem("amo_portal_token", storedToken);
    localStorage.setItem("amo_code", "AMO-A");
    localStorage.setItem("amo_slug", "tenant-a");
    localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_color_scheme", "light");
    sessionStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true, missing: [] }));
    localStorage.setItem("amo_current_user", JSON.stringify({
      id: "quality-user-a",
      amo_id: "amo-a",
      department_id: "department-quality",
      staff_code: "QMS-001",
      email: "quality@tenant-a.test",
      first_name: "Quality",
      last_name: storedRole === "AUDITOR" ? "Auditor" : "Manager",
      full_name: storedRole === "AUDITOR" ? "Quality Auditor" : "Quality Manager",
      role: storedRole,
      position_title: storedRole === "AUDITOR" ? "Quality Auditor" : "Quality Manager",
      is_active: true,
      is_superuser: false,
      is_amo_admin: false,
      must_change_password: false,
    }));
  }, { storedToken: token, storedRole: role });

  await page.route("**/auth/portal-preferences/", (route) => json(route, {
    user_id: "quality-user-a",
    amo_id: "amo-a",
    text_scale: "standard",
    density: "comfortable",
    motion: "system",
    color_scheme: "light",
    accent: "tenant",
    version: 1,
    updated_at: "2026-08-10T08:00:00Z",
  }));
  await page.route("**/accounts/admin/admin-profile/**", (route) => json(route, { eligible: false, active: false }));
  const handleQualityApiRequest = (route: Route) => {
    // Keep document navigations on the SPA server; only intercept data calls.
    if (route.request().resourceType() === "document") return route.continue();
    return qualityHandler(route, new URL(route.request().url()));
  };
  await page.route("**/api/maintenance/tenant-a/quality/**", handleQualityApiRequest);
  await page.route("http://127.0.0.1:8080/api/maintenance/tenant-a/quality/**", handleQualityApiRequest);
}

function emptyRegister(route: Route) {
  return json(route, { items: [], columns: [], limit: 30, offset: 0, next_offset: null, has_more: false });
}

function peopleResponses(route: Route, url: URL, canManage = true): Promise<void> | void {
  const path = url.pathname;
  if (path.endsWith("/quality/people/authorization-control/overview")) {
    return json(route, {
      permissions: {
        can_view: true,
        can_prepare: canManage,
        can_approve: canManage,
        can_review: canManage,
        can_approve_exemption: canManage,
        can_manage_policy: canManage,
        can_oversight: canManage,
        self_service_only: !canManage,
      },
      metrics: {
        active_authorizations: 1, suspended_authorizations: 0, expiring_within_60_days: 0,
        open_authorization_cases: 0, reviews_due: 0, active_controlled_exemptions: 0,
      },
      attention: [],
    });
  }
  if (path.endsWith("/quality/people/authorization-control/people")) {
    return json(route, {
      items: [{
        key: "quality-user-a", name: "Amina Wanjiku", staff_code: "QMS-018",
        home_role: "AUDITOR", department: "Quality", workforce_status: "Active",
        authorizations: [{ authorization: "Auditor", status: "ACTIVE", scope: "Global", expires_on: "2026-12-31" }],
        open_cases: 0,
      }],
      total: 1, limit: 100, offset: 0, has_more: false,
    });
  }
  if (path.endsWith("/quality/people/authorization-control/people/quality-user-a")) {
    return json(route, {
      person: {
        name: "Amina Wanjiku", staff_code: "QMS-018", home_role: "AUDITOR",
        department: "Quality", active: true,
      },
      appointments: [{
        function: "Internal Quality Auditor", status: "ACTIVE",
        effective_from: "2026-01-01", effective_until: null,
      }],
      authorizations: [{
        key: "priv-hangar-b", authorization: "Auditor", status: "ACTIVE", scope: "Global",
        effective_from: "2026-01-01", expires_on: "2026-12-31",
        last_reviewed: "2026-06-01", next_review_due: "2027-06-01", limitations: [],
        readiness: {
          authorization: "Auditor", as_of: "2026-09-22", status: "Ready for decision", hard_blockers: [],
          training: { status: "Current", current: true, developmental_exception: false, courses: [], required: [], missing: [] },
          development: {
            observed_audits: 3, target: 3, progress_label: "3 / 3",
            target_is_hard_gate: false, supervision_required: false, audit_participation: [],
          },
          annual_review: null, controlled_exemption: null, affected_assignments: [],
        },
      }],
      cases: [],
      audit_participation: { items: [], observed_completed: 3, observed_target: 3 },
    });
  }
  if (path.endsWith("/quality/people/authorization-control/cases")) return json(route, { items: [], total: 0, limit: 100, offset: 0, has_more: false });
  if (path.endsWith("/quality/people/authorization-control/reviews")) return json(route, { items: [] });
  if (path.endsWith("/quality/people/authorization-control/authorizations")) {
    return json(route, { items: [{
      key: "priv-hangar-b", person: "Amina Wanjiku", authorization: "Auditor", status: "ACTIVE",
      scope: "Global", effective_from: "2026-01-01", expires_on: "2026-12-31",
      last_reviewed: null, next_review_due: null, limitations: [],
    }] });
  }
  if (path.endsWith("/quality/people/rules")) {
    return json(route, { items: [{
      id: "rule-auditor", privilege_code: "AUDITOR_INTERNAL", title: "Auditor", privilege_type: "AUDITOR",
      required_training_course_codes: ["QMS-AUD"], independence_required: true, max_concurrent_assignments: 3,
      scope_schema: {}, is_active: true, updated_at: "2026-08-10T08:00:00Z",
    }] });
  }
  return undefined;
}

test("People uses authorization cases and does not duplicate audit assignment workflow", async ({ page }) => {
  await prepare(page, async (route, url) => {
    const handled = peopleResponses(route, url, true);
    if (handled) return handled;
    return emptyRegister(route);
  });

  await page.goto("/maintenance/tenant-a/quality?workspace=people", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Authorization governance", exact: true })).toBeVisible();
  await page.locator(".qms-authz-tabs").getByRole("button", { name: "People", exact: true }).click();
  await expect(page.getByText("Amina Wanjiku", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Nominate", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Batch nominate", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Check audit assignment/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Change privilege/i })).toHaveCount(0);
  await page.getByRole("button", { name: "Nominate", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Nominate person for Quality authorization" })).toBeVisible();
});

test("Governed inbox keeps notifications separate and undated source records neutral", async ({ page }) => {
  await prepare(page, async (route, url) => {
    if (url.pathname.endsWith("/work-inbox/summary")) return json(route, {
      assigned_to_me: 1, approvals: 0, overdue: 0, completed: 0, source_errors: [],
    });
    if (url.pathname.endsWith("/work-inbox/assigned-to-me")) return json(route, {
      items: [{ id: "risks:risk-1", record_id: "risk-1", source: "risks", source_label: "Risk assessment",
        title: "Risk control follow-up", status: "OPEN", due_date: null,
        route: "/maintenance/tenant-a/quality/risk/register?record=risk-1", watching: false }],
      total: 1, limit: 30, offset: 0, source_errors: [],
    });
    return emptyRegister(route);
  });
  await page.goto("/maintenance/tenant-a/quality/inbox/assigned-to-me", { waitUntil: "domcontentloaded" });
  const work = page.getByRole("article").filter({ hasText: "Risk control follow-up" });
  await expect(work).toContainText("No deadline");
  await expect(work).not.toContainText("overdue");
  await expect(work).not.toContainText("notification");
  await expect(page.getByRole("link", { name: "Open workflow" })).toHaveAttribute("href", "/maintenance/tenant-a/quality/risk/register?record=risk-1");
});

test("Quality work shows authorised counts, overdue urgency, source filtering and shared approval semantics", async ({ page }) => {
  await prepare(page, async (route, url) => {
    const path = url.pathname;
    if (path.endsWith("/work-inbox/summary")) return json(route, {
      assigned_to_me: 1, approvals: 1, overdue: 1, completed: 0, source_errors: [],
    });
    if (path.endsWith("/work-inbox/assigned-to-me")) {
      const source = url.searchParams.get("source");
      const items = source && source !== "audits" ? [] : [{
        id: "audits:audit-1", record_id: "audit-1", source: "audits",
        source_label: "Audit", title: "Audit finding follow-up", status: "CAP_OPEN",
        due_date: "2020-01-01", route: "/maintenance/tenant-a/quality/audits/audit-1/setup",
        watching: false,
      }];
      return json(route, { items, total: items.length, offset: 0, limit: 30, source_errors: [] });
    }
    if (path.endsWith("/work-inbox/approvals")) return json(route, {
      items: [], total: 0, offset: 0, limit: 30, source_errors: [],
    });
    return emptyRegister(route);
  });
  await page.goto("/maintenance/tenant-a/quality/inbox/assigned-to-me", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "My Quality Work" })).toBeVisible();
  await expect(page.getByText("Audit finding follow-up", { exact: true })).toBeVisible();
  await expect(page.getByText(/days overdue/)).toBeVisible();
  const open = page.getByRole("link", { name: "Open workflow" });
  await expect(open).toHaveAttribute("href", "/maintenance/tenant-a/quality/audits/audit-1/setup");
  await expect(page.locator(".qms-inbox__metric--attention")).toContainText("Overdue");
  await page.getByLabel("Quality source").selectOption("cars");
  await expect(page.getByText("Audit finding follow-up")).toHaveCount(0);
  await expect(page.getByText("No matching work")).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByText("Audit finding follow-up", { exact: true })).toBeVisible();
  await page.locator(".qms-inbox__metric").filter({ hasText: "Approvals" }).click();
  await expect(page.getByRole("heading", { name: "Management approvals" })).toBeVisible();
  await expect(page.getByText(/shared management queue/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "No pending management decisions" })).toBeVisible();
});

test("Watched cancelled, rejected and retired work retains its deadline without false urgency", async ({ page }) => {
  await prepare(page, async (route, url) => {
    if (url.pathname.endsWith("/work-inbox/summary")) return json(route, {
      assigned_to_me: 0, approvals: 0, overdue: 1, completed: 0, source_errors: [],
    });
    if (url.pathname.endsWith("/work-inbox/watching")) {
      const statuses = ["CANCELLED", "REJECTED", "RETIRED", "CLOSED", "OPEN"];
      return json(route, {
        items: statuses.map((status, index) => ({
          id: "reviews:review-" + index, record_id: "review-" + index,
          source: "reviews", source_label: "Management review",
          title: "Watched " + status.toLowerCase() + " review", status,
          due_date: "2020-01-01",
          route: "/maintenance/tenant-a/quality/management-review/review-" + index + "/overview",
          watching: true,
        })),
        total: statuses.length, limit: 30, offset: 0, source_errors: [],
      });
    }
    return emptyRegister(route);
  });
  await page.goto("/maintenance/tenant-a/quality/inbox/watching", { waitUntil: "domcontentloaded" });
  for (const status of ["cancelled", "rejected", "retired", "closed"]) {
    const work = page.getByRole("article").filter({ hasText: "Watched " + status + " review" });
    await expect(work).toBeVisible();
    await expect(work.locator(".qms-inbox__due")).not.toContainText("overdue");
    await expect(work.locator(".qms-inbox__due")).not.toContainText("Due in");
    await expect(work.locator(".qms-inbox__due")).toContainText("2020");
  }
  const active = page.getByRole("article").filter({ hasText: "Watched open review" });
  await expect(active.locator(".qms-inbox__due")).toContainText(/days overdue/);
});

test("Today focus ranks overdue personal and governed work without changing source authority", async ({ page }) => {
  await prepare(page, async (route, url) => {
    if (url.pathname.endsWith("/work-inbox/summary")) return json(route, {
      assigned_to_me: 1, overdue: 1, approvals: 1, completed: 0, source_errors: [],
    });
    if (url.pathname.endsWith("/work-inbox/assigned-to-me")) return json(route, {
      items: [{
        id: "risks:risk-1", record_id: "risk-1", source: "risks", source_label: "Risk assessment",
        title: "Review open hazard", status: "OPEN", due_date: "2020-01-01",
        next_action: "Review risk treatment in source", scope: "ASSIGNED",
        route: "/maintenance/tenant-a/quality/risk/register?record=risk-1", watching: false,
      }],
      total: 1, limit: 30, offset: 0, source_errors: [],
    });
    if (url.pathname.endsWith("/work-inbox/related")) return json(route, {
      items: [{ id: "provider-invitations:grant-1", record_id: "grant-1",
        source: "provider-invitations", source_label: "Provider invitation",
        title: "Confirm representative invite", status: "PENDING_VERIFICATION", due_date: null,
        next_action: "Review mail receipt and verification", scope: "SHARED_REVIEW",
        route: "/maintenance/tenant-a/quality/external-accounts?view=accounts&grant=grant-1",
      }],
      total: 1, limit: 30, offset: 0,
      source_errors: [{ source: "Document acknowledgement", message: "Unavailable source" }],
    });
    return emptyRegister(route);
  });
  await page.route("**/tasks/personal**", route => json(route, {
    items: [{
      id: "personal-1", title: "High urgency personal follow-up", description: "",
      due_at: "2020-01-01T10:00:00Z", status: "OPEN", priority: 1,
      entity_type: "quality_personal", metadata_json: {},
    }],
    total: 1, offset: 0, limit: 30,
  }));
  await page.goto("/maintenance/tenant-a/quality/inbox/assigned-to-me", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Today & next steps" }).click();
  const focus = page.getByRole("region", { name: "Today and next steps" });
  await expect(focus.getByRole("heading", { name: "Today & next steps" })).toBeVisible();
  await expect(focus.getByText("High urgency personal follow-up")).toBeVisible();
  await expect(focus.getByText("Review open hazard")).toBeVisible();
  await expect(focus.getByText("Confirm representative invite")).toBeVisible();
  await expect(focus.getByRole("alert")).toContainText("Document acknowledgement");
  const first = focus.locator(".qms-inbox__work-card").first();
  await expect(first).toContainText("High urgency personal follow-up");
  await expect(focus.getByRole("link", { name: "Open workflow" })).toHaveCount(2);
  await expect(focus.getByRole("button", { name: "Complete" })).toHaveCount(0);
  for (const width of [1920, 834, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 2);
  }
});

test("Connected work is scoped, next-action based and responsive without exposing mutation shortcuts", async ({ page }) => {
  await prepare(page, async (route, url) => {
    if (url.pathname.endsWith("/work-inbox/related")) {
      const source = url.searchParams.get("source") || "";
      const category = url.searchParams.get("category") || "all";
      const items = [
        { id: "training-steps:s1", record_id: "s1", source: "training-steps",
          source_label: "Training workflow", title: "Document training · Sign off",
          status: "PENDING", due_date: "2020-01-01", route: "/maintenance/tenant-a/training/competence",
          scope: "ASSIGNED", next_action: "Await activation of an earlier training step", blocked: true },
        { id: "document-acknowledgements:d1", record_id: "d1", source: "document-acknowledgements",
          source_label: "Document acknowledgement", title: "Acknowledge controlled distribution · Quality manual",
          status: "PENDING", due_date: "2020-01-01",
          route: "/maintenance/tenant-a/quality/documents/distribution",
          scope: "ASSIGNED", next_action: "Acknowledge the issued controlled document", blocked: false },
        { id: "provider-approvals:p1", record_id: "p1", source: "provider-approvals",
          source_label: "External provider account", title: "Review verified provider representative",
          status: "AWAITING_QUALITY_APPROVAL", due_date: null,
          route: "/maintenance/tenant-a/quality/external-accounts?view=accounts",
          scope: "SHARED_REVIEW", next_action: "Quality Manager to review the verified account grant", blocked: false },
      ].filter(item => (!source || item.source === source) &&
        (category !== "overdue" || item.due_date !== null));
      return json(route, { items, total: items.length, limit: 30, offset: 0, source_errors: [] });
    }
    if (url.pathname.endsWith("/work-inbox/summary")) return json(route, {
      assigned_to_me: 0, approvals: 0, overdue: 0, completed: 0, source_errors: [],
    });
    return emptyRegister(route);
  });
  await page.goto("/maintenance/tenant-a/quality/inbox/assigned-to-me", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Connected work" }).click();
  const area = page.getByRole("region", { name: "Connected Quality work" });
  await expect(area.getByRole("heading", { name: "Connected responsibilities" })).toBeVisible();
  await expect(area.getByText("Assigned to you").first()).toBeVisible();
  await expect(area.getByText("Shared decision queue")).toBeVisible();
  await expect(area.getByText("Await activation of an earlier training step")).toBeVisible();
  await expect(area.getByRole("link", { name: "Open source workspace" })).toHaveCount(3);
  await expect(area.getByRole("button", { name: "Complete" })).toHaveCount(0);
  await area.getByLabel("Connected source").selectOption("document-acknowledgements");
  await expect(area.getByRole("link", { name: "Open source workspace" })).toHaveCount(1);
  await expect(area.getByRole("link", { name: "Open source workspace" })).toHaveAttribute(
    "href", "/maintenance/tenant-a/quality/documents/distribution",
  );
  for (const width of [1920, 834, 390]) {
    await page.setViewportSize({ width, height: 900 });
    const docWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(docWidth).toBeLessThanOrEqual(width + 2);
  }
});

test("Vendor invitations distinguish Resend acceptance, sandbox and real delivery receipts", async ({ page }) => {
  const account = {
    grant_id: "grant-1", provider_id: "provider-1", supplier_id: 1, version: 1,
    legal_name: "Test Provider", supplier_code: "TP-001",
    email: "representative@example.test", display_name: "Test Representative",
    identity_id: "identity-1", role_code: "READ_ONLY", capabilities_json: [],
    object_scope_json: {}, grant_state: "PENDING", portal_state: "PENDING",
    identity_state: "INVITED", verified_at: null, restrict_new_work: false,
  };
  let mailed = false;
  await prepare(page, async (route, url) => {
    const path = url.pathname;
    if (path.endsWith("/quality/external-accounts/events")) return json(route, { items: [] });
    if (path.endsWith("/quality/external-accounts")) return json(route, { items: mailed ? [account] : [account] });
    if (path.includes("/quality/external-accounts/grants/grant-1/delivery-history"))
      return json(route, {
        grant_id: "grant-1", grant_status: "PENDING", verified: false,
        recipient: account.email, note: "Provider acceptance is not recipient-server delivery or inbox placement.",
        attempts: [{
          email_status: "SENT", email_delivery_status: "ACCEPTED",
          email_log_id: "log-1", provider_message_id: "email-resend-1",
          sending_mode: "SANDBOX", provider_accepted: true,
          attempted_at: "2026-11-19T08:30:00Z", recipient: account.email,
          effective_recipient: "sandbox@example.test", template_key: "external-provider-invitation",
          events: [{ event: "email.sent", at: "2026-11-19T08:30:00Z" }],
        }],
      });
    if (path.endsWith("/quality/external-accounts/suppliers")) return json(route, {
      items: [{ id: 1, supplier_code: "TP-001", legal_name: "Test Provider",
        status: "ACTIVE", is_active: true, external_import_pending_activation: false }],
      has_more: false,
    });
    if (path.endsWith("/quality/external-accounts/invitations") && route.request().method() === "POST") {
      mailed = true;
      return json(route, {
        id: "grant-1", status: "PENDING", delivery_status: "SENT",
        delivery: {
          email_status: "SENT", email_delivery_status: "ACCEPTED", email_log_id: "log-1",
          provider_message_id: "email-resend-1", sending_mode: "SANDBOX", provider_accepted: true,
        },
      }, 201);
    }
    return emptyRegister(route);
  });
  await page.goto("/maintenance/tenant-a/quality/external-accounts?view=accounts", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Inspect invitation delivery for Test Representative" }).click();
  const panel = page.getByRole("region", { name: "Provider invitation delivery history" });
  await expect(panel.getByText("Accepted by Resend — recipient delivery not confirmed")).toBeVisible();
  await expect(panel.getByText(/Sandbox routing was active/)).toBeVisible();
  await expect(panel.getByText("email-resend-1")).toBeVisible();
  await expect(panel.getByText("sandbox@example.test")).toBeVisible();
  await expect(panel).not.toContainText("one-time-secret");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(392);
});

test("Personal to-dos save reminders, complete, reopen and fit responsive viewports", async ({ page }) => {
  await prepare(page, async (route, url) => {
    if (url.pathname.endsWith("/work-inbox/summary")) return json(route, {
      assigned_to_me: 0, approvals: 0, overdue: 0, completed: 0, source_errors: [],
    });
    if (url.pathname.includes("/work-inbox/")) return json(route, {
      items: [], total: 0, offset: 0, limit: 30, source_errors: [],
    });
    return emptyRegister(route);
  });
  let tasks: Array<Record<string, unknown>> = [];
  await page.route("**/tasks/personal**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "GET") {
      const completed = url.searchParams.get("status") === "all";
      const search = (url.searchParams.get("q") || "").toLowerCase();
      const matching = tasks.filter(task => (completed || !["DONE", "CANCELLED"].includes(String(task.status)))
        && String(task.title).toLowerCase().includes(search));
      const limit = Number(url.searchParams.get("limit") || 25);
      const offset = Number(url.searchParams.get("offset") || 0);
      return json(route, { items: matching.slice(offset, offset + limit), total: matching.length, offset, limit });
    }
    const values = request.postDataJSON() as Record<string, unknown>;
    const id = request.method() === "POST" ? "personal-1" : url.pathname.split("/").pop();
    const previous = tasks.find(task => task.id === id);
    const task = { ...previous, ...values, id, amo_id: "amo-a", owner_user_id: "quality-user-a",
      entity_type: "quality_personal", status: values.status || previous?.status || "OPEN",
      metadata_json: { reminder_at: values.reminder_at },
      created_at: previous?.created_at || new Date().toISOString(), updated_at: new Date().toISOString(),
    };
    tasks = [task];
    return json(route, task, request.method() === "POST" ? 201 : 200);
  });
  await page.goto("/maintenance/tenant-a/quality/inbox/assigned-to-me", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Personal to-dos" }).click();
  const personal = page.getByRole("region", { name: "Personal to-do list" });
  await expect(personal.getByText("Plan your first follow-up")).toBeVisible();
  await personal.getByRole("button", { name: "New to-do" }).click();
  await personal.getByLabel("Task", { exact: true }).fill("Review new evidence");
  await personal.getByLabel("Email reminder", { exact: true }).fill("2026-10-12T09:30");
  await personal.getByRole("button", { name: "Save task" }).click();
  await expect(personal.getByText("Review new evidence", { exact: true })).toBeVisible();
  expect(tasks[0].metadata_json).toMatchObject({ reminder_at: new Date("2026-10-12T09:30").toISOString() });
  await personal.getByRole("button", { name: "Complete", exact: true }).click();
  await expect(personal.getByText("Review new evidence", { exact: true })).toHaveCount(0);
  await personal.getByLabel("Show completed").check();
  await personal.getByRole("button", { name: "Reopen", exact: true }).click();
  await expect(personal.getByRole("button", { name: "Complete", exact: true })).toBeVisible();
  expect(tasks[0].status).toBe("OPEN");
  for (const width of [1920, 834, 390]) {
    await page.setViewportSize({ width, height: 900 });
    const bounds = await personal.boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width + 2);
    const documentWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(documentWidth).toBeLessThanOrEqual(width + 2);
  }
});

test("Calendar fits desktop, split screen and phone widths", async ({ page }) => {
  await prepare(page, route => emptyRegister(route));
  await page.goto("/maintenance/tenant-a/quality/calendar/month", { waitUntil: "domcontentloaded" });
  // Assert route resolution separately so a redirect or permission failure is diagnosable.
  await expect(page).toHaveURL(/\/maintenance\/tenant-a\/quality\/calendar\/month(?:\?|$)/);
  // Calendar paths are owned by Planner V2, not the retired canonical register calendar.
  const planner = page.locator(".qms-modern-planner-v2");
  await expect(planner, "Planner V2 should mount for the canonical calendar route").toBeVisible({ timeout: 10_000 });
  const board = page.getByLabel("Quality month planner");
  const canvas = page.locator(".qms-planner-canvas");
  await expect(board, "The month grid should render within the Planner V2 canvas").toBeVisible();
  await expect(canvas).toBeVisible();

  for (const width of [1440, 800, 390]) {
    await page.setViewportSize({ width, height: 900 });
    const canvasBox = await canvas.boundingBox();
    expect(canvasBox, `Calendar canvas should remain present at ${width}px`).not.toBeNull();
    expect(canvasBox!.x + canvasBox!.width, `Calendar canvas must stay within the ${width}px viewport`).toBeLessThanOrEqual(width + 2);
    const documentWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(documentWidth, `Document must not overflow the ${width}px viewport`).toBeLessThanOrEqual(width + 2);

    if (width <= 800) {
      const scroll = await canvas.evaluate((element) => ({ clientWidth: element.clientWidth, scrollWidth: element.scrollWidth }));
      expect(scroll.scrollWidth, "Narrow month views should scroll inside the canvas, not the document").toBeGreaterThan(scroll.clientWidth);
    }
  }
  await page.screenshot({ path: "../.test-artifacts/quality-calendar-mobile.png", fullPage: true });
});

test("People read access does not expose mutation controls to a Quality Auditor", async ({ page }) => {
  await prepare(page, async (route, url) => {
    const handled = peopleResponses(route, url, false);
    if (handled) return handled;
    return emptyRegister(route);
  }, "AUDITOR");

  await page.goto("/maintenance/tenant-a/quality?workspace=people", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Authorization governance", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "My Authorization", exact: true })).toBeVisible();
  await expect(page.locator(".qms-authz-tabs").getByRole("button", { name: "People", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Authorization Cases", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Reviews", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Administration", exact: true })).toHaveCount(0);
  await expect(page.getByText("Amina Wanjiku", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Authorization record/i })).toBeVisible();
  await expect(page.getByRole("button", { name: "Nominate", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Batch nominate", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Record review/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Controlled exemption/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Suspend/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Revoke/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Check audit assignment/i })).toHaveCount(0);
});
