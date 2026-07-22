import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

const plannerHookSource = readSource("./hooks/useRosterPlannerDataV2.ts");
const rosterShellSource = readSource("./components/RosterShell.tsx");
const rosterPeopleSource = readSource("../../services/rosterPeople.ts");
const workOrdersSource = readSource("../../services/workOrders.ts");
const queryPersisterSource = readSource("../../services/queryPersister.ts");
const mainSource = readSource("../../main.tsx");
const themeContractSource = readSource("../../styles/theme-contract.css");
const themeRepairsSource = readSource("../../styles/theme-module-repairs.css");

describe("rostering architecture regressions", () => {
  it("keeps every rostering page inside the global department shell", () => {
    expect(rosterShellSource).toContain("<DepartmentLayout");
    expect(rosterShellSource).toContain('activeDepartment="rostering"');
    expect(rosterShellSource).toContain("</DepartmentLayout>");
  });

  it("uses stable query resources instead of a recursive load-all effect", () => {
    expect(plannerHookSource).toContain("useQuery({");
    expect(plannerHookSource).toContain("useInfiniteQuery({");
    expect(plannerHookSource).toContain('"eligible-people"');
    expect(plannerHookSource).toContain('"version-workspace"');
    expect(plannerHookSource).not.toContain("loadAll");
    expect(plannerHookSource).not.toContain("useEffect(() => void");
  });

  it("loads roster personnel through the paginated planner contract", () => {
    expect(rosterPeopleSource).toContain("/workforce/roster-people");
    expect(plannerHookSource).toContain("PEOPLE_PAGE_SIZE = 100");
    expect(plannerHookSource).toContain("getNextPageParam");
    expect(plannerHookSource).not.toContain("limit: 1000");
  });

  it("persists optimistic assignment rows in the version workspace", () => {
    expect(plannerHookSource).toContain("single source of assignment state");
    expect(plannerHookSource).toContain("setQueryData<VersionWorkspace>");
    expect(plannerHookSource).toContain("assignments: next");
    expect(plannerHookSource).not.toContain("useState<RosterAssignmentRead[]>([])");
  });

  it("passes bearer authentication to every work-order helper", () => {
    expect(workOrdersSource).toContain('import { authHeaders } from "./auth"');
    expect(workOrdersSource).toContain("headers: authHeaders()");
    expect(workOrdersSource.match(/headers: authHeaders\(\)/g)?.length).toBeGreaterThanOrEqual(11);
  });

  it("isolates persisted queries when the active AMO changes", () => {
    expect(queryPersisterSource).toContain("type ScopedPersistedClient");
    expect(queryPersisterSource).toContain("scope !== boundScope");
    expect(queryPersisterSource).toContain("currentOfflineScope() !== scope");
    expect(mainSource).toContain("clearTenantScopedRuntimeState");
    expect(mainSource).toContain("BRANDING_EVENT");
    expect(mainSource).toContain("ACTIVE_AMO_STORAGE_KEYS");
  });

  it("repairs legacy light surfaces after module CSS is loaded", () => {
    expect(themeContractSource).toContain(".admin-user-create-page");
    expect(themeContractSource).toContain("--portal-control-bg");
    expect(themeRepairsSource).toContain(".tc-hero");
    expect(themeRepairsSource).toContain(".manuals-hero-card");
    expect(themeRepairsSource).toContain(".platform-shell");
  });
});
