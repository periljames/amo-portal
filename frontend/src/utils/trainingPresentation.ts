export type TrainingCoursePresentationInput = {
  id?: string | null;
  course_id?: string | null;
  course_name?: string | null;
  kind?: string | null;
  status?: string | null;
  group_code?: string | null;
  prerequisite_course_id?: string | null;
  frequency_months?: number | null;
};

export type CanonicalTrainingType = "INITIAL" | "RECURRENT";

export function canonicalTrainingType(course: TrainingCoursePresentationInput | null | undefined): CanonicalTrainingType | null {
  if (!course) return null;
  const kind = String(course.kind || "").trim().toUpperCase();
  const status = String(course.status || "").trim().toUpperCase();
  if (kind === "INITIAL" || status === "INITIAL") return "INITIAL";
  if (["RECURRENT", "REFRESHER", "CONTINUATION", "RENEWAL"].includes(kind)) return "RECURRENT";
  if (["RECURRENT", "REFRESHER", "CONTINUATION", "RENEWAL"].includes(status)) return "RECURRENT";
  return null;
}

export function trainingTypeLabel(course: TrainingCoursePresentationInput | null | undefined): string {
  const type = canonicalTrainingType(course);
  if (type === "INITIAL") return "Initial";
  if (type === "RECURRENT") return "Recurrent";
  return "—";
}

export function explicitTrainingRequirementKey(course: TrainingCoursePresentationInput | null | undefined): string {
  if (!course) return "";
  const groupCode = String(course.group_code || "").trim();
  if (groupCode) return `group:${groupCode.toLocaleLowerCase()}`;
  const prerequisite = String(course.prerequisite_course_id || "").trim();
  if (prerequisite) return `prerequisite:${prerequisite.toLocaleLowerCase()}`;
  return `course:${String(course.id || course.course_id || "unknown")}`;
}

export function complianceStatusLabel(status: string | null | undefined): string {
  switch (String(status || "").toUpperCase()) {
    case "OVERDUE": return "Overdue";
    case "DUE_SOON": return "Due Soon";
    case "DEFERRED": return "Deferred";
    case "SCHEDULED_ONLY": return "Scheduled";
    case "NOT_DONE": return "Not completed";
    case "COMPLETED": return "Completed";
    case "OK": return "Current";
    default: return String(status || "Unknown").replaceAll("_", " ");
  }
}

export function isNonRecurrentInitial(course: TrainingCoursePresentationInput | null | undefined): boolean {
  return canonicalTrainingType(course) === "INITIAL" && !course?.frequency_months;
}

export function completedEventStatusWithoutRequirement(hasCompletion: boolean): "COMPLETED" | "NOT_DONE" {
  return hasCompletion ? "COMPLETED" : "NOT_DONE";
}
