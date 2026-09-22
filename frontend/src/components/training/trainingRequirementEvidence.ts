import type { TrainingFileRead } from "../../services/training";
import type { TrainingRecordRead } from "../../types/training";

export function latestEvidenceByRecord(files: TrainingFileRead[]): Map<string, TrainingFileRead> {
  const result = new Map<string, TrainingFileRead>();
  files
    .slice()
    .sort((a, b) => String(b.uploaded_at).localeCompare(String(a.uploaded_at)))
    .forEach((file) => {
      if (file.record_id && !result.has(file.record_id)) result.set(file.record_id, file);
    });
  return result;
}

export function filesByIdMap(files: TrainingFileRead[]): Map<string, TrainingFileRead> {
  const result = new Map<string, TrainingFileRead>();
  files.forEach((file) => result.set(file.id, file));
  return result;
}

/** Resolve certificate/evidence for a record via linked files or attachment_file_id. */
export function resolveRecordEvidence(
  record: TrainingRecordRead | null | undefined,
  latestByRecordId: Map<string, TrainingFileRead>,
  filesById: Map<string, TrainingFileRead>,
): TrainingFileRead | null {
  if (!record) return null;
  const byRecordLink = latestByRecordId.get(record.id);
  if (byRecordLink) return byRecordLink;
  const attachmentId = String(record.attachment_file_id || "").trim();
  if (!attachmentId) return null;
  return filesById.get(attachmentId) || null;
}

export function isPdfEvidence(file: TrainingFileRead): boolean {
  return (file.content_type || "").toLowerCase().includes("pdf") || file.original_filename.toLowerCase().endsWith(".pdf");
}
