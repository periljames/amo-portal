import { expect, it } from "vitest";
import { matchesQuestionHistory } from "./QuestionAuditHistory";

it("does not mistake a shared manual or regulation reference for the same question", () => {
  expect(matchesQuestionHistory({ checklist_ref: "SL/QMS/20", requirement_ref: "SL/QMS/20" }, "question-1", "SL/QMS/20")).toBe(false);
  expect(matchesQuestionHistory({ checklist_item_id: "question-2" }, "question-1", "1.2")).toBe(false);
  expect(matchesQuestionHistory({ checklist_item_id: "question-1" }, "question-1", "SL/QMS/20")).toBe(true);
  expect(matchesQuestionHistory({ checklist_ref: "Q7.10" }, "new-question-id", "Q7.10")).toBe(true);
});
