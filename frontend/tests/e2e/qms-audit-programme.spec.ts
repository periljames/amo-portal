import { expect, test, type Page, type Route } from "@playwright/test";

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: 4_102_444_800 })}.signature`;
}

function universeItem() {
  return {
    id: "universe-1",
    entity_type: "DEPARTMENT",
    display_label: "Maintenance Department",
    source_owner_module: "workforce",
    source_type: "DEPARTMENT",
    source_id: "maintenance",
    source_route: "/maintenance/tenant-a/rostering",
    risk_classification: "HIGH",
    regulatory_criticality: "HIGH",
    surveillance_interval_days: 365,
    mandatory_surveillance: true,
    active: true,
    notes: null,
  };
}

function programme(id = "programme-1", status = "APPROVED") {
  return {
    id,
    programme_ref: id === "programme-1" ? "AP-2026-BASE-R01" : "AP-2026-CREATED-R01",
    programme_series: id === "programme-1" ? "AP-2026-BASE" : "AP-2026-CREATED",
    programme_year: 2026,
    revision_no: 1,
    title: id === "programme-1" ? "2026 Approved Audit Programme" : "2026 Quality Audit Programme",
    assurance_model: "HYBRID",
    continuous_monitoring_enabled: true,
    optimizer_version: "HYBRID_ASSURANCE_V1",
    objectives: ["Verify continuing conformity and Quality-system effectiveness."],
    regulatory_basis: ["MPM Quality Audit Programme"],
    status,
    period_start: "2026-01-01",
    period_end: "2026-12-31",
    owner_user_id: "quality-user-a",
    supersedes_programme_id: null,
    approved_by_user_id: status === "APPROVED" ? "quality-user-a" : null,
    approved_at: status === "APPROVED" ? "2026-01-02T10:00:00Z" : null,
    activated_at: null,
    closed_at: null,
    created_at: "2026-01-01T08:00:00Z",
    updated_at: "2026-01-02T10:00:00Z",
    metrics: {
      planned_audit_count: 1,
      completed_audit_count: 0,
      deferred_audit_count: 0,
      cancelled_audit_count: 0,
      follow_up_audit_count: 0,
      scheduled_audit_count: 0,
      unscheduled_audit_count: 1,
    },
    readiness: {
      ready_for_approval: true,
      blockers: [],
      requirement_count: 1,
      mandatory_requirement_count: 1,
      mandatory_unscheduled_count: 1,
      high_risk_requirement_count: 1,
      unscheduled_requirement_count: 1,
      mandatory_coverage_gap_count: 0,
    },
    items: [{
      id: "programme-item-1",
      programme_id: id,
      universe_item_id: "universe-1",
      audit_type: "DEPARTMENTAL",
      title: "Maintenance Department Audit",
      purpose: "Annual internal surveillance",
      scope: "Maintenance procedures and execution controls",
      criteria: ["MPM"],
      mandatory_surveillance: true,
      recurrence: "ANNUAL",
      custom_interval_days: null,
      target_start: "2026-08-15",
      target_end: "2026-08-15",
      state: "PLANNED",
      prioritization_basis: [{
        driver: "HYBRID_ASSURANCE",
        algorithm: "HYBRID_ASSURANCE_V1",
        priority_score: 82,
        priority_band: "HIGH",
        components: { compliance: 85, risk: 75, performance: 46 },
      }],
      deferral_reason: null,
      cancellation_reason: null,
      auditable_entity: universeItem(),
    }],
    events: [{
      id: "event-1",
      event_type: "APPROVED",
      reason: "Approved annual surveillance plan.",
      before_snapshot: null,
      after_snapshot: { status: "APPROVED" },
      actor_user_id: "quality-user-a",
      created_at: "2026-01-02T10:00:00Z",
    }],
  };
}

function optimizer() {
  return {
    algorithm: "HYBRID_ASSURANCE_V1",
    weights: { compliance: 0.4, risk: 0.35, performance: 0.25 },
    as_of: "2026-08-23T09:00:00Z",
    assurance_model: "HYBRID",
    continuous_monitoring_enabled: true,
    recommendations: [{
      universe_item_id: "universe-1",
      auditable_entity: "Maintenance Department",
      entity_type: "DEPARTMENT",
      source_route: "/maintenance/tenant-a/rostering",
      algorithm: "HYBRID_ASSURANCE_V1",
      priority_score: 82,
      priority_band: "HIGH",
      recommended_interval_days: 90,
      components: { compliance: 85, risk: 75, performance: 46 },
      drivers: [],
      signals: {
        repeat_findings: 2,
        open_findings: 1,
        follow_up_required: 0,
        deferred_audits: 0,
        failed_controls: 0,
        adverse_trends: 0,
        last_audit_date: "2026-05-15",
      },
      mandatory_baseline: true,
      recommend_in_programme: true,
      recommended_in_current_programme: true,
      in_programme: true,
      programme_item_id: "programme-item-1",
      next_recommended_due: "2026-08-15",
      target_start: "2026-08-01",
      target_end: "2026-08-29",
      requires_amendment: false,
    }],
    summary: {
      auditable_entities: 1,
      recommended_current_period: 1,
      mandatory_baseline_due: 1,
      mandatory_coverage_gaps: 0,
      adaptive_risk_performance_coverage: 0,
      coverage_gaps: 0,
      requires_amendment: 0,
    },
  };
}

function schedulingQueue() {
  return {
    items: [{
      programme_id: "programme-1",
      programme_ref: "AP-2026-BASE-R01",
      programme_status: "APPROVED",
      programme_year: 2026,
      programme_revision_no: 1,
      programme_item_id: "programme-item-1",
      universe_item_id: "universe-1",
      auditable_entity: "Maintenance Department",
      audit_type: "DEPARTMENTAL",
      title: "Maintenance Department Audit",
      recurrence: "ANNUAL",
      mandatory_surveillance: true,
      target_start: "2026-08-15",
      target_end: "2026-08-15",
      prioritization_basis: [],
    }],
    total: 1,
    limit: 50,
    offset: 0,
    has_more: false,
  };
}

async function prepare(page: Page): Promise<void> {
  const token = futureToken();
  let programmes = [programme()];
  let current = programmes[0];

  const currentUser = {
    id: "quality-user-a",
    amo_id: "amo-a",
    department_id: "department-quality",
    staff_code: "QMS-001",
    email: "quality@tenant-a.test",
    first_name: "Quality",
    last_name: "Manager",
    full_name: "Quality Manager",
    role: "QUALITY_MANAGER",
    position_title: "Quality Manager",
    is_active: true,
    is_superuser: false,
    is_amo_admin: true,
    must_change_password: false,
    last_login_at: null,
    last_login_ip: null,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  };

  // Vite 5173/4173 uses same-origin API paths (getApiBaseUrl() === "").
  // Inject the session into sessionStorage (canonical token store) and keep a
  // localStorage copy only for the auth module's one-time migration path.
  await page.addInitScript(({ storedToken, storedUser }) => {
    sessionStorage.setItem("amo_portal_token", storedToken);
    localStorage.setItem("amo_portal_token", storedToken);
    localStorage.setItem("amo_code", "AMO-A");
    localStorage.setItem("amo_slug", "tenant-a");
    localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_color_scheme", "light");
    localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true, missing: [] }));
    sessionStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true, missing: [] }));
    localStorage.setItem("amo_current_user", JSON.stringify(storedUser));
    localStorage.setItem("amo_session_last_user_activity", String(Date.now()));
  }, { storedToken: token, storedUser: currentUser });

  const fulfil = async (route: Route) => {
    const request = route.request();
    // Never replace the SPA document/assets with JSON — that previously caused
    // navigations under /quality/... to render API error bodies instead of React.
    if (["document", "stylesheet", "script", "image", "font", "media", "manifest"].includes(request.resourceType())) {
      await route.continue();
      return;
    }

    const url = new URL(request.url());
    const path = url.pathname;

    if (path === "/readyz" || path === "/livez" || path === "/healthz" || path === "/health") {
      // RealtimeProvider/fetchHealthz requires process liveness shape ({ status: "alive" } or process: true).
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "alive", process: true, ready: true, live: true }),
      });
      return;
    }
    if (path === "/time") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ epoch_ms: Date.now() }),
      });
      return;
    }
    // Analytics beacons are same-origin portal URLs. A real 401 here trips
    // portalFetchErrorBridge → handleAuthFailure and clears the mocked session.
    if (path === "/platform/product-events" || path.startsWith("/platform/product-events?")) {
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    if (path.startsWith("/api/events")) {
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    if (path.endsWith("/auth/me") || path.includes("/auth/me?")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(currentUser) });
      return;
    }
    if (path.endsWith("/auth/refresh") && request.method() === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          access_token: token,
          token_type: "bearer",
          expires_in: 3600,
          user: currentUser,
          amo: { id: "amo-a", amo_code: "AMO-A", name: "Tenant A", login_slug: "tenant-a", data_mode: "REAL" },
          department: { id: "department-quality", code: "quality", name: "Quality" },
        }),
      });
      return;
    }
    if (path.includes("/auth/portal-preferences")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        user_id: "quality-user-a", amo_id: "amo-a", text_scale: "standard", density: "comfortable",
        motion: "system", color_scheme: "light", accent: "tenant", version: 1, updated_at: "2026-08-08T12:00:00Z",
      }) });
      return;
    }
    if (path.includes("/accounts/admin/admin-profile")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ eligible: false, active: false }) });
      return;
    }
    if (path.includes("/accounts/onboarding/status")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ is_complete: true, missing: [] }),
      });
      return;
    }
    // messagingApi.threads() expects a bare ChatThread[] (not { items: [] }).
    // A wrong shape crashes MessagingHub and can blank the authenticated shell.
    if (path.startsWith("/api/chat/threads")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
      return;
    }
    if (path.includes("/api/notifications/me/unread-count")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ notifications: 0, messages: 0, total: 0 }),
      });
      return;
    }
    if (path === "/api/maintenance/tenant-a/quality/audit-programmes" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: programmes, total: programmes.length, limit: 50, offset: 0, has_more: false }) });
      return;
    }
    if (path === "/api/maintenance/tenant-a/quality/audit-programmes" && request.method() === "POST") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      expect(payload).not.toHaveProperty("programme_methodology");
      expect(payload).not.toHaveProperty("methodology_rationale");
      current = programme("programme-created", "DRAFT");
      programmes = [...programmes, current];
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(current) });
      return;
    }
    if (path === "/api/maintenance/tenant-a/quality/audit-programmes/planner/queue" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(schedulingQueue()) });
      return;
    }
    if (path === "/api/maintenance/tenant-a/quality/audit-programmes/universe/items") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [universeItem()], total: 1, limit: 200, offset: 0, has_more: false }) });
      return;
    }
    const scheduleLinksMatch = path.match(/^\/api\/maintenance\/tenant-a\/quality\/audit-programmes\/([^/]+)\/schedule-links$/);
    if (scheduleLinksMatch && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], total: 0, limit: 50, offset: 0, has_more: false }) });
      return;
    }
    const optimizerMatch = path.match(/^\/api\/maintenance\/tenant-a\/quality\/audit-programmes\/([^/]+)\/optimizer(?:\/rebuild)?$/);
    if (optimizerMatch) {
      const result = optimizer();
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(request.method() === "POST" ? { ...result, sync: { added: 0, updated: 1 } } : result) });
      return;
    }
    if (path === "/api/maintenance/tenant-a/quality/integrations/calendar/schedule-options" || path === "/quality/integrations/calendar/schedule-options") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        timezone_name: "Africa/Nairobi",
        frequencies: ["ONE_TIME", "MONTHLY", "QUARTERLY", "BI_ANNUAL", "ANNUAL"],
        kinds: ["INTERNAL", "EXTERNAL", "THIRD_PARTY"],
        supported_source_types: [],
        unsupported_source_types: {},
        scopes: [{ id: "scope-internal", code: "INT", name: "Internal quality audit", party_level: "INTERNAL", default_kind: "INTERNAL" }],
        people: [{ id: "quality-user-a", full_name: "Quality Manager", email: "quality@tenant-a.test", role: "QUALITY_MANAGER", department_name: "Quality" }],
      }) });
      return;
    }
    const scheduleMatch = path.match(/^\/api\/maintenance\/tenant-a\/quality\/audit-programmes\/([^/]+)\/items\/([^/]+)\/schedule$/);
    if (scheduleMatch && request.method() === "POST") {
      const payload = request.postDataJSON() as { allow_conflicts?: boolean; conflict_override_reason?: string };
      if (!payload.allow_conflicts) {
        await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ detail: {
          message: "The proposed Quality commitment conflicts with active personnel or location allocations.",
          conflicts: [{
            subject_type: "AUDIT_SCHEDULE", subject_id: "existing-1", title: "Hangar surveillance",
            start_date: "2026-08-15", end_date: "2026-08-15", start_time: "09:00:00", end_time: "10:00:00",
            location: "Hangar 1", conflicting_user_ids: ["quality-user-a"], reason: "Responsible personnel or attendees overlap.",
          }],
        } }) });
        return;
      }
      expect(payload.conflict_override_reason).toContain("operationally separated");
      const base = programmes.find((entry) => entry.id === scheduleMatch[1]) || current;
      const scheduled = {
        ...base,
        metrics: { ...base.metrics, planned_audit_count: 0, scheduled_audit_count: 1 },
        items: (base.items || []).map((entry) => entry.id === scheduleMatch[2] ? { ...entry, state: "SCHEDULED" } : entry),
        events: [...(base.events || []), {
          id: "event-scheduled", event_type: "ITEM_SCHEDULED",
          reason: "Programme requirement scheduled in the authoritative Quality Planner after deterministic conflict validation.",
          before_snapshot: { state: "PLANNED" }, after_snapshot: { state: "SCHEDULED", schedule_id: "schedule-1" },
          actor_user_id: "quality-user-a", created_at: "2026-08-08T12:20:00Z",
        }],
      };
      programmes = programmes.map((entry) => entry.id === scheduleMatch[1] ? scheduled : entry);
      current = scheduled;
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({
        id: "schedule-1", amo_id: "amo-a", title: "Maintenance Department Audit", domain: "AMO", kind: "INTERNAL",
        audit_scope_id: "scope-internal", audit_scope_code: "INT", frequency: "ANNUAL", next_due_date: "2026-08-15",
        start_time: "09:00:00", end_time: "10:00:00", duration_days: 1, timezone_name: "Africa/Nairobi", location: "Hangar 1",
        lifecycle_status: "ACTIVE", version: 1, conflicts: [],
      }) });
      return;
    }
    const detailMatch = path.match(/^\/api\/maintenance\/tenant-a\/quality\/audit-programmes\/([^/]+)$/);
    if (detailMatch && request.method() === "GET") {
      const found = programmes.find((item) => item.id === detailMatch[1]) || current;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(found) });
      return;
    }
    const transitionMatch = path.match(/^\/api\/maintenance\/tenant-a\/quality\/audit-programmes\/([^/]+)\/transitions$/);
    if (transitionMatch && request.method() === "POST") {
      const payload = request.postDataJSON() as { target_status: string; reason: string };
      current = { ...current, status: payload.target_status, events: [...(current.events || []), {
        id: "event-transition", event_type: "SUBMITTED_FOR_REVIEW", reason: payload.reason,
        before_snapshot: { status: "DRAFT" }, after_snapshot: { status: payload.target_status }, actor_user_id: "quality-user-a", created_at: "2026-08-08T12:10:00Z",
      }] };
      programmes = programmes.map((item) => item.id === transitionMatch[1] ? current : item);
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(current) });
      return;
    }
    if (path.includes("/api/maintenance/tenant-a/quality/") || path.startsWith("/quality/")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], columns: [], limit: 25, offset: 0, has_more: false }) });
      return;
    }
    if (path.startsWith("/auth/") || path.startsWith("/api/") || path.startsWith("/accounts/") || path.startsWith("/platform/")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) });
      return;
    }
    await route.continue();
  };

  // Same-origin (5173/4173) and direct-8080 API traffic both must be mocked.
  // Document navigations under /maintenance/.../quality/... continue above.
  await page.route("**/*", fulfil);
}

test("opens hybrid programme, optimizer and Audit Universe lineage", async ({ page }) => {
  await prepare(page);
  await page.goto("/maintenance/tenant-a/quality/audits/program", { waitUntil: "domcontentloaded" });

  // Quality context chrome hides AuditPageShell's h1 title block; assert the
  // live programme workspace surface instead of the suppressed page heading.
  await expect(page.getByLabel("Audit Programme workspace")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Programme workspace sections" })).toBeVisible();
  await expect(page.getByText("AP-2026-BASE-R01", { exact: false }).first()).toBeVisible();
  await expect(page.getByRole("region", { name: "Hybrid assurance optimizer" })).toBeVisible();
  await expect(page.getByText("Hybrid · Always on", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("2 repeat finding signal(s)", { exact: false })).toBeVisible();
  await expect(page.getByRole("region", { name: "Programme scheduling queue" })).toBeVisible();
  await expect(page.getByText("Maintenance Department Audit", { exact: true }).first()).toBeVisible();

  await page.getByRole("button", { name: "Universe" }).click();
  await expect(page.getByRole("heading", { name: "Audit Universe", exact: true })).toBeVisible();
  await expect(page.getByText("Maintenance Department", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("workforce · DEPARTMENT", { exact: true })).toBeVisible();
});

test("creates a hybrid draft without a methodology choice and requires a reason before review", async ({ page }) => {
  await prepare(page);
  await page.goto("/maintenance/tenant-a/quality/audits/program", { waitUntil: "domcontentloaded" });

  await page.getByRole("button", { name: "New programme" }).click();
  await expect(page.getByRole("dialog", { name: "Create programme" })).toBeVisible();
  await expect(page.getByRole("radio")).toHaveCount(0);
  await expect(page.getByLabel(/Compliance baseline/i)).toBeVisible();
  await page.getByRole("button", { name: "Create draft programme" }).click();

  const detailHeader = page.locator(".qms-audit-programme__detail-header");
  await expect(page.getByText("AP-2026-CREATED-R01", { exact: false }).first()).toBeVisible();
  await expect(detailHeader.getByText("Draft", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Readiness" }).click();
  const submitReview = page.getByRole("button", { name: "Submit for review" });
  await expect(submitReview).toBeDisabled();
  await page.getByLabel("Programme transition reason").fill("Ready for independent Quality review.");
  await expect(submitReview).toBeEnabled();
  await submitReview.click();
  await expect(detailHeader.getByText("Under Review", { exact: true })).toBeVisible({ timeout: 10_000 });
  await page.locator(".qms-audit-programme-flow__history > summary").click();
  await expect(page.locator(".qms-audit-programme-flow__history").getByText("Ready for independent Quality review.", { exact: true })).toBeVisible();
});

test("programme requirement uses planner conflict gate before schedule lineage is committed", async ({ page }) => {
  await prepare(page);
  await page.goto("/maintenance/tenant-a/quality/audits/program", { waitUntil: "domcontentloaded" });

  const queue = page.getByRole("region", { name: "Programme scheduling queue" });
  await queue.getByRole("button", { name: /Maintenance Department Audit/i }).click();
  await expect(page.getByRole("dialog", { name: "Schedule into Planner V2" })).toBeVisible();
  await expect(page.getByLabel("Schedule audit programme requirement")).toBeVisible();
  await expect(page.getByLabel("Frequency")).toHaveValue("ANNUAL");
  await expect(page.getByLabel("Date")).toHaveValue("2026-08-15");
  await page.getByLabel("Location").fill("Hangar 1");
  await page.getByLabel("Lead auditor").selectOption("quality-user-a");
  await page.getByRole("button", { name: "Create authoritative schedule" }).click();

  await expect(page.getByRole("region", { name: "Planner conflicts" })).toBeVisible();
  await expect(page.getByText("Hangar surveillance", { exact: true })).toBeVisible();
  await page.getByLabel("Conflict override reason").fill("Activities are operationally separated with independent coverage.");
  await page.getByRole("button", { name: "Create with governed override" }).click();

  await expect(page.getByText("Schedule created", { exact: false })).toBeVisible();
  await expect(page.getByText("schedule-1", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open in Planner" })).toBeVisible();
});

test("programme schedule deep-link stays inside Audit Assurance chrome", async ({ page }) => {
  await prepare(page);
  await page.goto(
    "/maintenance/tenant-a/quality/audits/program/programme-1/items/programme-item-1/schedule",
    { waitUntil: "domcontentloaded" },
  );

  await expect(page.getByLabel("Audit Assurance sections")).toBeVisible();
  await expect(page.getByRole("tab", { name: /Programme/i })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("heading", { name: "Schedule programme requirement", exact: true })).toBeVisible();
  await expect(page.getByLabel("Frequency")).toHaveValue("ANNUAL");
});
