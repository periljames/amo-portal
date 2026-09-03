import { describe, expect, it } from "vitest";

import { ApiClientError } from "../../../services/apiClient";
import {
  auditOccurrenceLoadDetail,
  auditPrerequisiteLoadDetail,
} from "./auditStageLoadErrorMessages";

describe("audit stage load error messages", () => {
  it("turns occurrence 404s into tenant-aware recovery guidance", () => {
    const message = auditOccurrenceLoadDetail(
      new ApiClientError(404, "QMS API 404: Not Found", { detail: "Not Found" }),
    );

    expect(message).toContain("current AMO");
    expect(message).toContain("Setup");
    expect(message).not.toContain("404");
  });

  it("turns child-stage 404s into prerequisite guidance", () => {
    const prerequisite = "Complete preparation before opening Live.";

    expect(auditPrerequisiteLoadDetail(
      new ApiClientError(404, "Not Found", { detail: "Not Found" }),
      prerequisite,
    )).toBe(prerequisite);
  });

  it("does not present authorization failures as missing stages", () => {
    const message = auditPrerequisiteLoadDetail(
      new ApiClientError(403, "Forbidden", { detail: "Forbidden" }),
      "Complete preparation before opening Live.",
    );

    expect(message).toContain("cannot access");
    expect(message).not.toContain("preparation");
  });
});
