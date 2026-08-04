# Training Tracker workbook → AMO Portal functional mapping

The workbook is a migration and reconciliation source. It is not retained as the operating interface after a controlled import.

| Workbook sheet | Source purpose | Portal destination | Import behaviour |
|---|---|---|---|
| `People` | Personnel master, employment status, department, position, KAMEL/E-AMEL/G-AMEL and internal certification details | Personnel register, access review, individual Training Profile and licence register | Imported after row-level identity matching. New people require an explicit `CREATE_ACCOUNT`, `PROFILE_ONLY`, or `SKIP` decision. Multiple licence authorities are retained. |
| `Courses` | Course catalogue, recurrence, category, mandatory flag, scope and reference | Course Requirements → Catalogue | CourseID-based idempotent create/update. |
| `Training` | Completion history, renewals, due dates and source status | Individual training record log and compliance engine | Person/course/date deduplication, lifecycle reconciliation and immutable audit event. |
| `tblRoleGroups` | Applicability group definitions | Course Requirements → Applicability groups | Tenant-scoped role groups. |
| `tblPersonRoles` | Person-to-role-group assignments | Personnel profile and requirement resolution | Supports several active training roles for one person. |
| `tblCourseMatrix` | Course-to-role-group mandatory rules | Course Requirements → Matrix | Imported as backend-owned applicability rules used by compliance calculations and scheduling. |
| `Params` | Workbook policy defaults | Tenant Training policy settings | Mapped configuration; not copied as operational rows. |
| `Overdue` | Formula-driven exception view | Live Overdue/Due-soon personnel queues | Recomputed from authoritative portal records. |
| `Next_Batch` | Formula/macro candidate list for the next class | Smart scheduler and roster builder | Recomputed using live requirements, expiry and availability. |
| `Individual_Lookup` | Individual printable record and licence lookup | Training Profile and Personnel Training Record PDF | Live profile, licence register, history and evidence. |
| `Course_Audit` | Missing prerequisite/follow-up checks | Data rectification queue | Backend-owned exception results; no duplicate spreadsheet data. |
| `Sheet1` | Helper lists | Internal portal lookups | Reference-only; not imported as operational data. |

## Controlled import stages

1. Upload and hash the workbook.
2. Discover visible and hidden worksheets.
3. Validate and match every operational row.
4. Show actual row progress and the current worksheet/record.
5. Require decisions for new personnel and identity conflicts.
6. Commit courses, personnel/licences, role groups, matrix rules and training history in dependency order.
7. Reconcile created, updated, unchanged, skipped and failed rows.
8. Record an immutable audit event and retain the bounded row-level import report.

## Safety controls

- Every job and imported entity is AMO-scoped.
- Repeated file hashes are identified before commit.
- Training history uses the existing renewal and record-lifecycle controls.
- New People rows never silently create accounts.
- A personnel-only profile is supported when a person must exist in training records but should not receive portal access.
- Matrix rules are evaluated by the backend compliance engine, not inferred by the frontend.
- Derived workbook sheets are represented by live portal capabilities rather than duplicated stored calculations.
