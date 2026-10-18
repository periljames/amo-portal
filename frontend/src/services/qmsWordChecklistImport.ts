import type { ChecklistResponseOption, ChecklistTemplateItem, UploadedChecklistDraft } from "./qmsChecklistTemplates";

export type WordChecklistCell = { text: string; span?: number };
const compact = (value: string) => value.replace(/\s+/g, "").toUpperCase();
const clean = (value: string) => value.replace(/[ \t]+/g, " ").trim();
const statuses: Record<string, ChecklistResponseOption["canonical_status"]> = {
  YES: "COMPLIANT", Y: "COMPLIANT", S: "COMPLIANT",
  NO: "NONCOMPLIANT", N: "NONCOMPLIANT", U: "NONCOMPLIANT",
  "N/A": "NOT_APPLICABLE", "N/C": "NOT_VERIFIED",
};

/** Only numbered rows under an explicit assessment header are audit questions. */
export function extractWordChecklistTables(tables: WordChecklistCell[][][]): ChecklistTemplateItem[] {
  const items: ChecklistTemplateItem[] = [];
  for (const rows of tables) {
    let section = "";
    let subsection = "";
    let options: ChecklistResponseOption[] = [];
    for (const cells of rows) {
      const texts = cells.map(cell => clean(cell.text));
      const ref = texts[0]?.replace(/\s+/g, "") || "";
      const labels = texts.slice(2).filter(Boolean);
      if (cells.length >= 5 && labels.length >= 3 && labels.every(label => statuses[compact(label)])) {
        section = texts[1];
        subsection = "";
        options = labels.map(label => ({ value: compact(label), label: compact(label), canonical_status: statuses[compact(label)] }));
        continue;
      }
      if (!section) continue;
      if (!/^\d+(?:\.\d+)*[.)]?$/.test(ref)) {
        // Subheadings occupy the first column; remarks span the whole table.
        if (texts[0] && !texts.slice(1).some(Boolean) && (cells[0].span || 1) < 3 && !/^remarks\b/i.test(texts[0])) subsection = texts[0];
        continue;
      }
      if (cells.length < options.length + 2 || !texts[1]) continue;
      items.push({
        checklist_ref: ref, section: subsection ? `${section} / ${subsection}` : section,
        prompt: texts[1], response_type: "CUSTOM", response_options: options.map(option => ({ ...option })),
        applicability: "APPLICABLE", mandatory: true, na_justification_required: true,
        notes_required_when: ["NONCOMPLIANT", "NOT_APPLICABLE"], sort_order: items.length,
      });
    }
  }
  return items;
}

export async function importWordChecklist(file: File): Promise<UploadedChecklistDraft> {
  if (!file.size || file.size > 10 * 1024 * 1024) throw new Error("Choose a nonempty Word checklist under 10 MB.");
  const buffer = await file.arrayBuffer();
  const mammoth = await import("mammoth");
  const result = await mammoth.convertToHtml({ arrayBuffer: buffer });
  // Parse in an inert document. Uploaded markup is never inserted into the page.
  const document = new DOMParser().parseFromString(result.value, "text/html");
  const tables = Array.from(document.querySelectorAll("table")).map(table =>
    Array.from(table.rows).map(row => Array.from(row.cells).map(cell => ({
      text: Array.from(cell.querySelectorAll("p")).map(p => p.textContent || "").join("\n") || cell.textContent || "",
      span: cell.colSpan,
    }))),
  );
  const items = extractWordChecklistTables(tables);
  if (!items.length) throw new Error("No numbered questions with explicit response columns were found. Use a table with a question number, question and assessment headers.");
  const sha256 = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", buffer))).map(value => value.toString(16).padStart(2, "0")).join("");
  return { filename: file.name, sha256, items, question_count: items.length, section_count: new Set(items.map(item => item.section)).size, warnings: [] };
}
