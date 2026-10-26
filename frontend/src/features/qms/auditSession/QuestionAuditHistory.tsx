import { useQuery } from "@tanstack/react-query";
import { readAuditOfflinePack } from "../../../services/qmsAuditOfflinePack";

/** Match explicit question references only; audit-wide history is not question history. */
export function matchesQuestionHistory(row: Record<string, unknown>, itemId: string, checklistRef?: string | null) {
  return row.checklist_item_id === itemId
    || Boolean(checklistRef && /^(?:Q)?\d+(?:[.\-]\d+)*$/i.test(checklistRef) && row.checklist_ref === checklistRef);
}
export default function QuestionAuditHistory({ amoCode, auditId, itemId, checklistRef, requirementRef }: {
  amoCode: string; auditId: string; itemId: string; checklistRef?: string | null; requirementRef?: string | null;
}) {
  const history = useQuery({ queryKey: ["qms", "question-history-pack", amoCode, auditId],
    queryFn: () => readAuditOfflinePack(amoCode, auditId), networkMode: "always", staleTime: 30_000 });
  const snapshot = history.data?.work_package.package_snapshot;
  const groups = [
    { title: "Previous findings", rows: snapshot?.prior_findings || [] },
    { title: "Corrective action plans", rows: snapshot?.prior_cars || [] },
  ];
  return <section className="audit-question-history" aria-label="Question history"><h3>Previous evidence & corrective actions</h3>
    {groups.map(({ title, rows }) => {
      const related = rows.filter((row) => matchesQuestionHistory(row, itemId, checklistRef));
      return <div key={title}><h4>{title}</h4>{related.length ? <ul>{related.map((row, index) => <li key={String(row.id || index)}>
        <span>{String(row.finding_ref || row.car_ref || row.reference || title)}</span>
        <p>{String(row.statement || row.description || row.corrective_action || row.title || "")}</p>
        {typeof row.objective_evidence === "string" && row.objective_evidence ? <blockquote>{row.objective_evidence}</blockquote> : null}
        {row.status ? <small>{String(row.status).replaceAll("_", " ")}</small> : null}
      </li>)}</ul> : <p>{history.isPending ? "Loading saved history…" : history.isError ? "Saved history could not be loaded." : "No linked records available on this device."}</p>}</div>;
    })}
  </section>;
}
