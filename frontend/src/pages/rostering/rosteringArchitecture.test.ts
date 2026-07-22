import { describe, expect, it } from "vitest";

import plannerHookSource from "./hooks/useRosterPlannerDataV2.ts?raw";
import rosterShellSource from "./components/RosterShell.tsx?raw";
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
    expect(plannerHookSource).toContain('"eligible-people"');
    expect(plannerHookSource).toContain('"version-workspace"');
    expect(plannerHookSource).not.toContain("loadAll");
    expect(plannerHookSource).not.toContain("useEffect(() => void");
  });

  it("repairs legacy light surfaces after module CSS is loaded", () => {
    expect(themeContractSource).toContain(".admin-user-create-page");
    expect(themeContractSource).toContain("--portal-control-bg");
    expect(themeRepairsSource).toContain(".tc-hero");
    expect(themeRepairsSource).toContain(".manuals-hero-card");
    expect(themeRepairsSource).toContain(".platform-shell");
  });
});
