from pathlib import Path
from textwrap import indent


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if old in text:
        return text.replace(old, new, 1)
    if new in text:
        return text
    raise RuntimeError(f"Missing {label} anchor")


# ---------------------------------------------------------------------------
# Reuse the existing governance component in Setup while leaving submitted
# roster decisions in Command.
# ---------------------------------------------------------------------------
governance_path = "frontend/src/pages/rostering/components/RosterGovernancePanel.tsx"
governance = read(governance_path)
governance = replace_once(
    governance,
    "  canManageAuthorities,\n}: {",
    "  canManageAuthorities,\n  showApprovalWorkflow = true,\n}: {",
    label="governance destructuring",
)
governance = replace_once(
    governance,
    "  canManageAuthorities: boolean;\n}) {",
    "  canManageAuthorities: boolean;\n  showApprovalWorkflow?: boolean;\n}) {",
    label="governance prop type",
)
governance = replace_once(
    governance,
    "    enabled: Boolean(effectiveVersionId),",
    "    enabled: Boolean(effectiveVersionId) && showApprovalWorkflow,",
    label="approval matrix gate",
)
if "{showApprovalWorkflow ? (" not in governance:
    heading = '<div><h2>Roster approval</h2></div>'
    heading_position = governance.index(heading)
    section_start = governance.rfind('      <section className="wr-panel">', 0, heading_position)
    if section_start < 0:
        raise RuntimeError("Roster approval section start not found")
    section_end = governance.index("      </section>", heading_position) + len("      </section>")
    block = governance[section_start:section_end]
    wrapped = "      {showApprovalWorkflow ? (\n" + indent(block, "  ") + "\n      ) : null}"
    governance = governance[:section_start] + wrapped + governance[section_end:]
write(governance_path, governance)


# ---------------------------------------------------------------------------
# Restore reachable rule editing and approval-authority management in Setup.
# ---------------------------------------------------------------------------
setup_path = "frontend/src/pages/rostering/components/RosteringSetupWorkspace.tsx"
setup = read(setup_path)
setup = replace_once(
    setup,
    'import type { ShiftTemplateKind, ShiftTemplateRead } from "../../../types/rostering";',
    'import { listAllRosterPeople } from "../../../services/rosterPeople";\nimport type { ShiftTemplateKind, ShiftTemplateRead } from "../../../types/rostering";',
    label="roster people import",
)
setup = replace_once(
    setup,
    'import { EmptyState, RosterLoading, StatusPill } from "./RosterShell";',
    'import { RosterGovernancePanel } from "./RosterGovernancePanel";\nimport { RosterRuleQuickEditor } from "./RosterRuleQuickEditor";\nimport { EmptyState, RosterLoading, StatusPill } from "./RosterShell";',
    label="governance component imports",
)
setup = replace_once(
    setup,
    '    enabled: section === "calendar",',
    '    enabled: section === "calendar" || section === "policy",',
    label="policy periods query gate",
)
if "const governancePeopleQuery = useQuery" not in setup:
    rules_anchor = "  const rulesQuery = useQuery({"
    query_block = '''  const governancePeopleQuery = useQuery({
    queryKey: ["rostering", "settings", "governance-people"],
    queryFn: () => listAllRosterPeople({
      page_size: 250,
      active_only: true,
      roster_eligible_only: false,
    }),
    enabled: section === "policy",
    staleTime: 15 * 60_000,
  });
'''
    setup = setup.replace(rules_anchor, query_block + rules_anchor, 1)
if "const governancePeople = useMemo" not in setup:
    permission_anchor = "  const permissions = permissionsQuery.data?.permissions || [];\n"
    derived = '''  const governancePeople = useMemo(
    () => governancePeopleQuery.data?.items || [],
    [governancePeopleQuery.data?.items],
  );
  const governanceBases = useMemo(() => {
    const map = new Map<string, { id: string; code: string }>();
    governancePeople.forEach((person) => {
      if (!person.primary_base_station_id) return;
      map.set(person.primary_base_station_id, {
        id: person.primary_base_station_id,
        code: person.primary_base_code || "BASE",
      });
    });
    return [...map.values()].sort((left, right) => left.code.localeCompare(right.code));
  }, [governancePeople]);
'''
    setup = setup.replace(permission_anchor, permission_anchor + derived, 1)

policy_section = setup.index('{section === "policy" ? (')
policy_call_start = setup.index("        <PolicyPanel", policy_section)
policy_call_end = setup.index("        />", policy_call_start) + len("        />")
policy_call = '''        <PolicyPanel
          rules={rulesQuery.data || []}
          loading={rulesQuery.isPending}
          authorityCount={readiness.active_approval_authority_count}
          canManageRules={can("roster.manage_rules")}
          canManageAuthorities={can("roster.manage_approval_authorities")}
          people={governancePeople}
          periods={periodsQuery.data || []}
          bases={governanceBases}
          governanceLoading={governancePeopleQuery.isPending || periodsQuery.isPending}
          governanceError={governancePeopleQuery.error || periodsQuery.error}
        />'''
setup = setup[:policy_call_start] + policy_call + setup[policy_call_end:]

panel_start = setup.index("function PolicyPanel({")
panel_body = setup.index("  const groups = useMemo", panel_start)
panel_header = '''function PolicyPanel({
  rules,
  loading,
  authorityCount,
  canManageRules,
  canManageAuthorities,
  people,
  periods,
  bases,
  governanceLoading,
  governanceError,
}: {
  rules: Awaited<ReturnType<typeof listRosterRules>>;
  loading: boolean;
  authorityCount: number;
  canManageRules: boolean;
  canManageAuthorities: boolean;
  people: Awaited<ReturnType<typeof listAllRosterPeople>>["items"];
  periods: Awaited<ReturnType<typeof listRosterPeriods>>;
  bases: Array<{ id: string; code: string }>;
  governanceLoading: boolean;
  governanceError: unknown;
}) {
'''
setup = setup[:panel_start] + panel_header + setup[panel_body:]

if "showApprovalWorkflow={false}" not in setup:
    summary_marker = '<section className="wr-panel rs-approval-summary">'
    summary_start = setup.index(summary_marker, panel_start)
    summary_end = setup.index("</section>", summary_start) + len("</section>")
    controls = '''{canManageRules ? <RosterRuleQuickEditor /> : null}
      <section className="wr-panel rs-approval-summary"><div><CheckCircle2 size={20} /><span><strong>{authorityCount}</strong> active approval authority record{authorityCount === 1 ? "" : "s"}</span></div><p>Approval authorities define review and publishing scopes. Configure them here; submitted roster decisions remain in Command.</p></section>
      {governanceError ? <div className="wr-inline-error" role="alert">{errorMessage(governanceError)}</div> : null}
      {governanceLoading ? <RosterLoading label="Loading approval authorities…" /> : (
        <RosterGovernancePanel
          people={people}
          periods={periods}
          bases={bases}
          canManageRules={canManageRules}
          canManageAuthorities={canManageAuthorities}
          showApprovalWorkflow={false}
        />
      )}'''
    setup = setup[:summary_start] + controls + setup[summary_end:]
write(setup_path, setup)


# ---------------------------------------------------------------------------
# Expose canonical attendance variance evidence through the HR dashboard.
# ---------------------------------------------------------------------------
schema_path = "backend/amodb/apps/workforce/hr_schemas.py"
schema = read(schema_path)
schema = replace_once(
    schema,
    "from typing import Literal, Optional",
    "from typing import Any, Literal, Optional",
    label="schema Any import",
)
if "class HrAttendanceExceptionRead" not in schema:
    exception_schema = '''class HrAttendanceExceptionRead(HrSchema):
    id: str
    amo_id: str
    roster_assignment_id: str
    user_id: str
    user_full_name: Optional[str] = None
    planned_minutes: int
    attendance_minutes: int
    productive_minutes: int
    variance_minutes: int
    classification: str
    metadata_json: Optional[dict[str, Any]] = None
    calculated_at: datetime


'''
    schema = schema.replace("class HrOvertimeDecisionRequest(HrSchema):", exception_schema + "class HrOvertimeDecisionRequest(HrSchema):", 1)
if "attendance_exceptions:" not in schema:
    schema = schema.replace(
        "    pending_overtime: list[HrOvertimeRequestRead]\n    people: list[HrPersonReadiness]",
        "    pending_overtime: list[HrOvertimeRequestRead]\n    attendance_exceptions: list[HrAttendanceExceptionRead] = Field(default_factory=list)\n    people: list[HrPersonReadiness]",
        1,
    )
write(schema_path, schema)

service_path = "backend/amodb/apps/workforce/hr_service.py"
service = read(service_path)
if "def serialize_attendance_exception" not in service:
    serializer = '''def serialize_attendance_exception(
    row: models.RosterActualVariance,
    *,
    user: Optional[account_models.User] = None,
) -> hr_schemas.HrAttendanceExceptionRead:
    return hr_schemas.HrAttendanceExceptionRead(
        id=row.id,
        amo_id=row.amo_id,
        roster_assignment_id=row.roster_assignment_id,
        user_id=row.user_id,
        user_full_name=_display_name(user),
        planned_minutes=row.planned_minutes,
        attendance_minutes=row.attendance_minutes,
        productive_minutes=row.productive_minutes,
        variance_minutes=row.variance_minutes,
        classification=row.classification,
        metadata_json=row.metadata_json if isinstance(row.metadata_json, dict) else None,
        calculated_at=row.calculated_at,
    )


'''
    service = service.replace("def list_overtime_requests(", serializer + "def list_overtime_requests(", 1)
if "attendance_users_by_id" not in service:
    attendance_query = service.index("    attendance_exception_rows =")
    actions_position = service.index("    actions: list[hr_schemas.HrActionItem]", attendance_query)
    user_map = '''    attendance_user_ids = sorted({row.user_id for row in attendance_exception_rows})
    attendance_users = (
        db.query(account_models.User).filter(
            account_models.User.amo_id == amo_id,
            account_models.User.id.in_(attendance_user_ids),
        ).all()
        if attendance_user_ids
        else []
    )
    attendance_users_by_id = {str(user.id): user for user in attendance_users}

'''
    service = service[:actions_position] + user_map + service[actions_position:]
if 'category="ATTENDANCE"' not in service:
    sort_position = service.index("    actions.sort(")
    attendance_actions = '''    for row in attendance_exception_rows[:20]:
        actions.append(hr_schemas.HrActionItem(
            id=f"attendance:{row.id}",
            category="ATTENDANCE",
            severity="ACTION",
            title="Attendance variance requires review",
            detail=(
                f"{row.classification}: {row.variance_minutes:+d} minutes variance; "
                f"{row.attendance_minutes} attendance minutes against {row.planned_minutes} planned."
            ),
            user_id=row.user_id,
            user_name=_display_name(attendance_users_by_id.get(str(row.user_id))),
            due_on=row.calculated_at.date(),
            action_label="Inspect variance",
            action_path=f"time/attendance/{row.id}",
        ))
'''
    service = service[:sort_position] + attendance_actions + service[sort_position:]
if "attendance_exceptions=[" not in service:
    people_field = "        people=people,"
    attendance_response = '''        attendance_exceptions=[
            serialize_attendance_exception(
                row,
                user=attendance_users_by_id.get(str(row.user_id)),
            )
            for row in attendance_exception_rows
        ],
'''
    service = service.replace(people_field, attendance_response + people_field, 1)
write(service_path, service)


types_path = "frontend/src/types/workforceHr.ts"
types = read(types_path)
if "export type HrAttendanceException" not in types:
    attendance_type = '''export type HrAttendanceException = {
  id: string;
  amo_id: string;
  roster_assignment_id: string;
  user_id: string;
  user_full_name?: string | null;
  planned_minutes: number;
  attendance_minutes: number;
  productive_minutes: number;
  variance_minutes: number;
  classification: string;
  metadata_json?: Record<string, unknown> | null;
  calculated_at: string;
};

'''
    types = types.replace("export type HrDashboard = {", attendance_type + "export type HrDashboard = {", 1)
if "attendance_exceptions: HrAttendanceException[];" not in types:
    types = types.replace(
        "  pending_overtime: HrOvertimeRequest[];\n  people: HrPersonReadiness[];",
        "  pending_overtime: HrOvertimeRequest[];\n  attendance_exceptions: HrAttendanceException[];\n  people: HrPersonReadiness[];",
        1,
    )
write(types_path, types)


workforce_path = "frontend/src/pages/rostering/components/WorkforceHrWorkspace.tsx"
workforce = read(workforce_path)
workforce = replace_once(
    workforce,
    '    if (item.category === "TIMESHEET" || item.category === "OVERTIME") return <button type="button" className="hr-action-link" onClick={() => onOpen("time")}>{item.action_label || "Review time"} <ArrowRight size={13} /></button>;',
    '    if (["TIMESHEET", "OVERTIME", "ATTENDANCE"].includes(item.category)) return <button type="button" className="hr-action-link" onClick={() => onOpen("time")}>{item.action_label || "Review time"} <ArrowRight size={13} /></button>;',
    label="attendance action routing",
)
if "dashboard.attendance_exceptions.map" not in workforce:
    time_panel = workforce.index("function TimePanel(")
    mini_grid = workforce.index('      <section className="hr-mini-grid">', time_panel)
    attendance_panel = '''      <section className="wr-panel">
        <div className="wr-section-heading"><div><span className="wr-eyebrow">Attendance reconciliation</span><h2>Attendance exceptions</h2><p>These canonical variances identify the employee, roster assignment and measured difference requiring review.</p></div><span className="wr-header-badge"><Clock3 size={15} /> {dashboard.attendance_exceptions.length} shown</span></div>
        <div className="hr-approval-list">{dashboard.attendance_exceptions.map((exception) => <article key={exception.id}><div><strong>{exception.user_full_name || exception.user_id}</strong><span>{exception.calculated_at.slice(0, 16).replace("T", " ")} · assignment {exception.roster_assignment_id}</span><small>{exception.attendance_minutes} attendance · {exception.productive_minutes} productive · {exception.planned_minutes} planned minutes</small></div><StatusPill value={exception.classification} /><strong className={exception.variance_minutes === 0 ? "" : "is-danger"}>{exception.variance_minutes > 0 ? "+" : ""}{exception.variance_minutes} min</strong></article>)}</div>
        {!dashboard.attendance_exceptions.length ? <EmptyState title="No attendance exceptions" description="Roster-to-attendance variances will appear here with employee and assignment evidence." /> : null}
      </section>
'''
    workforce = workforce[:mini_grid] + attendance_panel + workforce[mini_grid:]
write(workforce_path, workforce)


# ---------------------------------------------------------------------------
# Focused regression contracts.
# ---------------------------------------------------------------------------
backend_test_path = "backend/amodb/apps/workforce/tests/test_pr364_final_review_regressions.py"
backend_test = read(backend_test_path)
if "test_attendance_exception_serializes_canonical_evidence" not in backend_test:
    backend_test += '''


def test_attendance_exception_serializes_canonical_evidence():
    row = SimpleNamespace(
        id="variance-1",
        amo_id="amo-1",
        roster_assignment_id="assignment-1",
        user_id="employee-1",
        planned_minutes=480,
        attendance_minutes=430,
        productive_minutes=410,
        variance_minutes=-50,
        classification="UNDER_RECORDED",
        metadata_json={"source": "attendance"},
        calculated_at=datetime(2026, 7, 29, 18, tzinfo=timezone.utc),
    )
    user = SimpleNamespace(full_name="Amina Engineer")

    result = hr_service.serialize_attendance_exception(row, user=user)

    assert result.user_full_name == "Amina Engineer"
    assert result.roster_assignment_id == "assignment-1"
    assert result.variance_minutes == -50
    assert result.metadata_json == {"source": "attendance"}
'''
write(backend_test_path, backend_test)

frontend_test_path = "frontend/src/pages/rostering/rosteringSetupExperience.test.ts"
frontend_test = read(frontend_test_path)
if 'expect(setupWorkspaceSource).toContain("RosterRuleQuickEditor")' not in frontend_test:
    frontend_test = frontend_test.replace(
        '    expect(setupWorkspaceSource).toContain("Compliance rules");',
        '    expect(setupWorkspaceSource).toContain("Compliance rules");\n    expect(setupWorkspaceSource).toContain("RosterRuleQuickEditor");\n    expect(setupWorkspaceSource).toContain("RosterGovernancePanel");\n    expect(setupWorkspaceSource).toContain("showApprovalWorkflow={false}");\n    expect(setupWorkspaceSource).toContain("roster.manage_approval_authorities");',
        1,
    )
if 'expect(workforceSource).toContain("dashboard.attendance_exceptions.map")' not in frontend_test:
    frontend_test = frontend_test.replace(
        '    expect(workforceSource).toContain("dashboard.can_approve_timesheet_hr");',
        '    expect(workforceSource).toContain("dashboard.can_approve_timesheet_hr");\n    expect(workforceSource).toContain("dashboard.attendance_exceptions.map");\n    expect(workforceSource).toContain("roster_assignment_id");',
        1,
    )
write(frontend_test_path, frontend_test)
