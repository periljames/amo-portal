# CAR register and finding case review

The live baseline used QAR/MO/26/006 and its three existing simulated CARs. This review changes presentation and workflow guards; it does not submit responses as the auditee or create additional findings or CARs. A labelled test PDF was attached by James to the existing simulated CAR/SAF/26/005 to verify evidence capture and retrieval.

## Findings and changes

| Problem | Result |
|---|---|
| Six row buttons, long repeated statements and tall summary tiles dominated the register | Compact summary strip, two-line statement previews, one Open action and a secondary action popover |
| Filters used large rounded controls with inconsistent alignment | Aligned rectangular filters, workflow queues and an Assigned to me selector |
| Opening a CAR produced a single-row register | A case view presents the owner, deadline, finding, next action, response, review notes, evidence and activity history |
| Users could enter review before a response existed | Review controls require an actual submitted response, the proper state and the existing server permission |
| A generic action drawer exposed unrelated queries and arbitrary status selection | The register opens the case and governed action plan; assignment editing and evidence attachment remain explicit permitted actions |
| Finding details called the acknowledger the owner and substituted audit scope for missing evidence | Responsible person and acknowledgement are separate; absent evidence remains explicitly absent |
| Finding-register linked CARs omitted their assignee display names | Linked CARs receive the same bounded server enrichment as the CAR register, so Elvin remains visible in both case views |
| A finding drawer combined Verify and Close and treated creation as acceptance | Both finding views share the same case component; verification, acknowledgement and closure use their actual recorded dates |
| Finding detail requested an unregistered canonical read URL and received a generic HTTP 200 list, then crashed while reading `rows[0]` | The tenant-bound paged finding-register read has an exact route owner; frontend contract checks and local error handling reject malformed responses |
| Observation detail offered CAR creation | Observations show observation follow-up and do not offer nonconformity CAR creation |
| Files attached to a question before raising its finding disappeared from the finding evidence filter | The backend includes same-audit, same-tenant source-question artifacts as well as directly linked finding files |
| Submitted RCA/CAP could appear as effectiveness work; returned responses could appear as implementation | Frontend labels and server workflow filters now consider review decisions as well as CAR status |
| A closed CAR could falsely make an unclosed finding appear closed | The finding remains in closeout/effectiveness review until its own closure is recorded |
| Accepting a plan could automatically close an unconfigured CAR and its finding | Acceptance leaves implementation open. Explicit governed implementation, evidence and effectiveness controls own closure |
| Evidence reads used a write-access gate | CAR evidence reads use the existing tenant-scoped view permission; modifying and reviewing remain separately guarded |
| Closed/cancelled internal CAR evidence could still receive uploads | The backend rejects uploads to closed, cancelled and escalated CARs before file storage |
| A floating effectiveness tool appeared on registers and unrelated pending case views | It is confined to the dedicated assurance context; case pages retain their own action-plan controls |
| Date-only deadlines were converted through UTC midnight, displaying the preceding day in this timezone | The register, case and action-plan views share local date-only formatting; the saved 16 January deadline remains 16 January |

## Role perspective

- **Auditor:** source requirement and objective evidence, auditee response, review notes and the next permitted review or closeout step.
- **Quality officer:** response and review queues, assignment and dates, evidence capture and a traceable activity history.
- **Quality manager:** team workload, overdue work and clear distinctions between proposed plans, implementation and effectiveness. Management access does not bypass the assigned-lead review gate.
- **Accountable executive:** owner, deadline, priority, escalation and assurance state without mutation controls granted by presentation alone. Escalated CARs identify Executive review as their next action.

The UI uses permission checks and server-provided capabilities; it does not pretend to switch roles. Live browser checks use James's authorized session. Other role accounts are not impersonated.

## Validation

- 47 backend tests passed, covering exact route ownership, workflow filters, source-question evidence isolation, view permission, locked evidence, acceptance without premature closure and the existing control-loop/evidence-pack paths.
- 29 frontend tests passed for register response contracts, next-action labels, review availability, dates, finding lifecycle and effectiveness-tool placement.
- TypeScript and the production build passed. The 49-modal check and heavy-route checks passed; large-chunk build warnings remain.

Live Chrome checks at 1440×1000 and 390×844 passed for register → CAR case → finding → CAR case → register, action-menu dismissal with Escape, the action-plan workspace and its return link, and the Observation view. The register, CAR case, finding and action-plan page had no horizontal document overflow at the phone viewport. Register status labels measured about **22px** high and rows about **82px**, with one Open action and one menu trigger each. The saved **16 January 2027** deadline remained 16 January in the register and case; Elvin appeared as the responsible person in both CAR and finding views.

Observation did not offer CAR creation or an unrelated floating effectiveness action. Its actual dark theme reported a dark surface (`rgb(45, 42, 38)`) and light text (`rgba(255,255,255,.96)`). Evidence attachment returned HTTP 201; downloading and reopening the attachment after reload succeeded, with SHA-256 `71e3a7eff34f0657fb9e894e2614d1285fb291058a4d9a09a960c74a4340c96f` matching the source PDF. The next action remained Auditee response; no review was enabled or submitted.

The API was restored under the supervised development runtime. `/livez` and `/readyz` returned HTTP 200. Private screenshots, receipts and measurements are under `.artifacts/audit-workflow-run/`, including `car-register-after.png`, `car-register-phone.png`, `car-case-desktop.png`, `finding-case-desktop.png`, `observation-case-theme.png` and `car-case-live-ui.json`.

These are browser viewport checks using James's session and isolated backend permission/workflow tests. They do not establish a live login under each other role, physical mobile-camera behavior, all-module offline coverage or independent-device synchronization. CAR evidence upload was tested online; a new durable offline CAR-file queue is not claimed.
