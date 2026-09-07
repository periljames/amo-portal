import { describe, expect, it } from "vitest";

import { uniqueById } from "./auditDashboardModel";

describe("audit assurance dashboard identity", () => {
  it("keeps one row when the API repeats an audit identifier", () => {
    const auditId = "8c77c7d2-364c-49fd-8513-79dea6c1e638";

    expect(uniqueById([
      { id: auditId, title: "Work Pack Audit" },
      { id: auditId, title: "Work Pack Audit duplicate" },
      { id: "second-audit", title: "Second audit" },
    ])).toEqual([
      { id: auditId, title: "Work Pack Audit" },
      { id: "second-audit", title: "Second audit" },
    ]);
  });
});
