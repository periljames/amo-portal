# Audit workflow repair — 18 October 2026

This continues the frontend-only run of **QAR/MO/26/006** after the owner authorized backend repairs. All live workflow writes use frontend controls. Automated transaction tests use the isolated test database; no live audit rows were seeded or edited with SQL.

## Why the finding questions did not retain NO

The atomic endpoint received the package's composed `APIRouter`, which exposed finding creation helpers but omitted `_serialize_finding`. Creating a finding reached response serialization, raised `AttributeError`, and rolled back the entire transaction—including its NO answer and CAR. A real ORM transaction test reproduced this exact exception when configured with the same router export; using the implementation module had concealed it.

The missing serializer export is repaired and covered by the router contract and transaction tests. Levels 1–3 commit the approved noncompliant source answer, finding, linked CAR and receipt together. Invalid source answers roll back all writes; repeating an accepted mutation returns its receipt without duplicate findings or CARs.

The frontend applies the returned row immediately. Unsubmitted finding drafts now show their selected answer with **Finding draft · not submitted**, including after local recovery. A later failure is not represented as a committed finding. Accepted finding reconciliation runs in the background and does not clear a different question's newly opened composer.

## Other repaired defects

- **Observation:** classification is separate from the approved source response. Level 4 can retain an auditor-selected YES/NO/N/A source answer without inventing an Observation column. The backend validates that answer against the frozen source scheme. Levels 1–3 still require a noncompliant decision. The guarded offline queue accepts this same contract. Observation counts use Level 4 finding records.
- **Notice email:** the configured sandbox destination contained two semicolon-separated addresses. They were being sent as one mailbox. Recipient parsing now validates and deduplicates comma/semicolon lists and passes separate mailboxes to the provider. Configuration validation rejects malformed addresses and line breaks. Sandbox routing remains enabled. This matches the provider's [recipient-list interface](https://resend.com/docs/api-reference/emails/send-email).
- **Word extraction:** physical merged cells are handled once, spaced assessment headers are normalized, identity tables are excluded, and workshop subheadings are retained. The supplied SL-QMS-29 REV 01 produces **189 questions / 14 groups / YES–NO–N/A** in the backend as well as the frontend. The existing S/U/N/C/N/A form remains supported.
- **Offline evidence review:** a bounded, user/tenant/audit-scoped AES-GCM cache retains synchronized uploads and explicitly opened downloads. Pending uploads are removed only after acceptance and checksum verification; cached reading copies are separate and may be evicted at the 50 MB per-user limit. Offline reads verify the artifact checksum and current scope. Failure to retain a reading copy does not turn a successful online download into a failed business action.
- **Phone controls:** finding drafts wrap with 44px targets. Auditee release controls move into the team/activity menu when its host is available, preserving a fallback if the fieldwork workspace fails. Release surfaces use theme tokens instead of a fixed white background.

## Live results

The existing simulated audit and approved checklist were retained. The running API was restored under the supervised local runtime after backend reload interrupted it.

| Question | Level | Finding | CAR | Accepted source answer |
|---|---|---|---|---|
| 1.1 | Critical | QAR/MO/26/006-F-001 | CAR/SAF/26/003 | NO |
| 5.7 | Major | QAR/MO/26/006-F-002 | CAR/SAF/26/004 | NO |
| 8.4 | Minor | QAR/MO/26/006-F-003 | CAR/SAF/26/005 | NO |
| 2.6 | Observation | QAR/MO/26/006-F-004 | None, as defined for Level 4 | YES |

Each finding returned HTTP 200 with a committed checklist row. The observed nonconformity radios show NO. All **189 questions are answered**; this count alone is not a claim that every lifecycle stage is complete. All assessment text is explicitly simulated, not an operational inspection or compliance certification.

Notice `QAR/MO/26/006/N01` was retried through **Send notice and email**. Dispatch returned **2 sent, 0 failed**, message IDs for both intended-recipient dispatch records, and notice status DELIVERED. The configured sandbox destinations still control actual routing. Provider acceptance and the application's DELIVERED status do not establish receipt in James's Proton mailbox or independent mailbox delivery.

## Checks

- 28 finding/email backend tests passed, including real ORM transactions, rollback, source-compatible observations, idempotent replay and recipient parsing.
- 12 parser tests passed, including the supplied Word document and the existing legacy form.
- 53 focused frontend tests passed, including encrypted retained evidence, hash rejection, scope isolation, storage failure, offline finding policy and journal recovery.
- The production build passed TypeScript, the 49-modal check and heavy-route checks. Large-chunk warnings remain; these checks do not certify performance on every device or network.

Live receipts, screenshots, runtime logs and test output are retained under the ignored `.artifacts/audit-workflow-run/` directory. Final release, offline opening and CAR handoff observations follow below.
