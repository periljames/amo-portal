import { describe, expect, it } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import TrainingRequirementList, { buildRows } from "./TrainingRequirementList";
import type { TrainingCourseRead, TrainingRecordRead, TrainingStatusItem } from "../../types/training";
import type { TrainingFileRead } from "../../services/training";
const course = (id: string, extra = {}): TrainingCourseRead => ({ id, course_pk: id, course_id: id.toUpperCase(), course_name: id, amo_id: "test", ...extra });
const record = (id: string, course_id: string, extra = {}): TrainingRecordRead => ({ id, course_id, amo_id: "test", user_id: "person", completion_date: "2026-01-01", ...extra });
const status = (course_id: string, extra = {}): TrainingStatusItem => ({ course_id, course_name: course_id, status: "OK", is_mandatory: true, ...extra });
const courses = [course("initial", { kind: "INITIAL" }), course("recurrent", { kind: "RECURRENT", prerequisite_course_id: "INITIAL" })];
const records = [record("old", "initial"), record("latest", "recurrent")];
const file: TrainingFileRead = { id: "certificate", amo_id: "test", owner_user_id: "person", record_id: "latest", kind: "CERTIFICATE", original_filename: "certificate.pdf", storage_path: "test", review_status: "APPROVED", uploaded_at: "2026-01-01" };
describe("training profile register", () => {
 it("keeps prerequisite records in one requirement history and uses recurrent evidence for same-day completions", () => {
  const rows = buildRows([status("recurrent"), status("initial")], courses, records, [file]);
  expect(rows).toHaveLength(1);
  expect(rows[0].history).toHaveLength(2);
  expect(rows[0].latestRecord?.id).toBe("latest");
  expect(rows[0].evidence?.id).toBe("certificate");
 });
 it("does not resurface required-course records under Other training", () => {
  const rows = buildRows([status("recurrent", { course_pk: "recurrent" })], courses, records, [file]);
  expect(rows).toHaveLength(1);
  const html = renderToStaticMarkup(<TrainingRequirementList items={[status("recurrent", { course_pk: "recurrent" })]} courses={courses} records={records} files={[file]} canEdit={false} />);
  expect(html).not.toContain("Other training");
 });
 it("does not collapse unresolved courses into one unknown requirement", () => {
  expect(buildRows([status("unknown-a"), status("unknown-b")], [], [], [])).toHaveLength(2);
 });
 it("places mandatory requirements ahead of overdue optional courses", () => {
  const rows = buildRows([status("a", { is_mandatory: false, status: "OVERDUE" }), status("b")], [course("a"), course("b")], [], []);
  expect(rows.map((row) => row.item.course_id)).toEqual(["b", "a"]);
 });
 it("uses course_pk aliases and does not recalculate authoritative deferred status", () => {
  const rows = buildRows([status("CODE", { course_pk: "recurrent", status: "DEFERRED" })], courses, [record("r", "CODE", { course_pk: "recurrent" })], []);
  expect(rows[0].latestRecord?.id).toBe("r");
  expect(rows[0].status).toBe("Deferred");
 });
 it("offers renewal and download together for an expired certificate without displaying duplicate initial training", () => {
  const html = renderToStaticMarkup(<TrainingRequirementList items={[status("recurrent", { status: "OVERDUE" })]} courses={courses} records={records} files={[file]} canEdit onRecordCompletion={() => {}} onDownloadEvidence={() => {}} />);
  expect(html).toContain("Upload renewed certificate for recurrent");
  expect(html).toContain("Download certificate for recurrent");
  expect(html).not.toContain("Other training");
 });
 it("does not expose upload, renewal, edit or delete to read-only users", () => {
  const html = renderToStaticMarkup(<TrainingRequirementList items={[status("recurrent", { status: "OVERDUE" })]} courses={courses} records={records} files={[]} canEdit={false} onRecordCompletion={() => {}} onUploadEvidence={() => {}} onEditRecord={() => {}} onDeleteRecord={() => {}} />);
  expect(html).not.toContain("Upload"); expect(html).not.toContain("Renew"); expect(html).not.toContain("Edit record"); expect(html).not.toContain("Delete record");
 });
});
