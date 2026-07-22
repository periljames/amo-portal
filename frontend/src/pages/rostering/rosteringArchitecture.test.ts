import { describe, expect, it } from "vitest";

import plannerHookSource from "./hooks/useRosterPlannerDataV2.ts?raw";
import rosterShellSource from "./components/RosterShell.tsx?raw";
import rosterPeopleSource from "../../services/rosterPeople.ts?raw";
import themeContractSource from "../../styles/theme-contract.css?raw";
import themeRepairsSource from "../../styles/theme-module-repairs.css?raw";

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

  it("repairs legacy light surfaces after module CSS is loaded", () => {
    expect(themeContractSource).toContain(".admin-user-create-page");
    expect(themeContractSource).toContain("--portal-control-bg");
    expect(themeRepairsSource).toContain(".tc-hero");
    expect(themeRepairsSource).toContain(".manuals-hero-card");
    expect(themeRepairsSource).toContain(".platform-shell");
  });
});
