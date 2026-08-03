import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd());

const servicePath = path.join(root, "src/services/reliability.ts");
let service = fs.readFileSync(servicePath, "utf8");
service = service.replace(
  `export const addEffectivenessReview = (caseId: number, payload: Record<string, unknown>, approve = false): Promise<EffectivenessReview> =>
  reliabilityMutation(\`/reliability/fracas/cases/\${caseId}/effectiveness?approve=\${approve}\`, "POST", payload);`,
  `export const addEffectivenessReview = (caseId: number, payload: Record<string, unknown>): Promise<EffectivenessReview> =>
  reliabilityMutation(\`/reliability/fracas/cases/\${caseId}/effectiveness\`, "POST", payload);
export const approveEffectivenessReview = (caseId: number, reviewId: string, rationale: string): Promise<EffectivenessReview> =>
  reliabilityMutation(\`/reliability/fracas/cases/\${caseId}/effectiveness/\${encodeURIComponent(reviewId)}/approve\`, "POST", { rationale });`,
);
fs.writeFileSync(servicePath, service.replace(/\s+$/, "") + "\n", "utf8");

const viewPath = path.join(root, "src/pages/reliability/ReliabilityAdvancedViews.tsx");
let view = fs.readFileSync(viewPath, "utf8");
view = view.replace("import React, { useCallback, useEffect, useMemo, useState } from \"react\";", "import React, { useCallback, useEffect, useState } from \"react\";");
view = view.replace("  addFracasEvidence,\n", "  addFracasEvidence,\n  approveEffectivenessReview,\n");
view = view.replace(
  `void action(() => addEffectivenessReview(caseId, { review_date: data.get("review_date"), metric_code: data.get("metric_code") || null, baseline_value: data.get("baseline_value") || null, current_value: data.get("current_value") || null, acceptance_criteria: data.get("acceptance_criteria"), outcome: data.get("outcome"), evidence_json: [], notes: data.get("notes") || null }, data.get("approve") === "on"));`,
  `void action(() => addEffectivenessReview(caseId, { review_date: data.get("review_date"), metric_code: data.get("metric_code") || null, baseline_value: data.get("baseline_value") || null, current_value: data.get("current_value") || null, acceptance_criteria: data.get("acceptance_criteria"), outcome: data.get("outcome"), evidence_json: [], notes: data.get("notes") || null }));`,
);
view = view.replace('<label className="reliability-v2__check-label"><input type="checkbox" name="approve" />Approve this review</label>', '<p className="reliability-v2__permission-note">A second authorised verifier must approve the review after it is recorded.</p>');
view = view.replace(
  `<small>{review.review_date} · {review.approved_at ? \`Approved \${displayDate(review.approved_at)}\` : "Not approved"}</small><p>{review.notes}</p></div>`,
  `<small>{review.review_date} · {review.approved_at ? \`Approved \${displayDate(review.approved_at)}\` : "Not approved"}</small><p>{review.notes}</p>{!review.approved_at && <button className="btn btn-small" type="button" disabled={!hasCapability(capabilities, "reliability.fracas.verify")} onClick={() => { const rationale = window.prompt("Independent effectiveness approval rationale"); if (rationale) void action(() => approveEffectivenessReview(caseId, review.id, rationale)); }}>Approve independently</button>}</div>`,
);
fs.writeFileSync(viewPath, view.replace(/\s+$/, "") + "\n", "utf8");
console.log("Independent Reliability approvals wired to the frontend.");
