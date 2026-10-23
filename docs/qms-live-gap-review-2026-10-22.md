# Live QMS gap review

This review used the authenticated Safarilink administrator/Quality account on the public Tailscale portal. It is distinct from browser fixtures. No invitations, approvals, maintenance releases or test business records were created.

The first pass visited 43 shared register destinations through their real menus and captured every page. Contact sheets were visually inspected. Some first-pass images caught loading transitions; they exposed prior-register rows under a new page title and must not be treated as settled-page acceptance evidence. An intermittent HTTP 500 occurred on Audit performance; a direct recheck returned 200. No matching failed API request appeared in the backend access log, so the gateway transport path was investigated. This is evidence of an intermittent failure, not proof that the report query itself failed.

| Area | Destinations checked | Finding / next governed work |
| --- | ---: | --- |
| My Quality Work | 5 | Personal to-dos obscured the main assignment register. Collapse optional to-dos; isolate data by current register/filter. Workflow semantics remain open: the Completed view still exposed action-required notices and some rows lacked actionable source links/deadlines. Notification receipt/read state must not be treated as task completion. |
| Risk & Opportunities | 5 | Register/matrix/opportunity/treatment/trend destinations render a shared read register. A matrix view is not yet a functioning risk assessment workflow. SMS authority, matrix configuration, controls, residual-risk acceptance and action ownership need dedicated verification. |
| System & Processes | 5 | Process/scope/objective registers load, but complete controlled editing, ownership, measurement and review workflows have not been demonstrated. |
| Controlled Documents | 5 | Shared library/change/approval/distribution/obsolete views are not proof of DMS authoring, publication or acknowledgement. Connect and verify the authoritative Document Control workflows rather than creating duplicate generic forms. |
| Equipment & Calibration | 7 | Read views do not establish equipment creation, certificate acceptance, calibration scheduling, quarantine/out-of-tolerance impact assessment or scrapping. Those transactions still need an authoritative operational owner reachable from QMS. |
| External Interface | 6 | Findings, complaints, feedback, correspondence, commitments and responses remain generic read views. Intake, ownership, deadlines, evidence, response approval and closure need dedicated workflow verification. |
| Management Review | 5 | Dashboard/meeting/action views are not a governed meeting workflow. Inputs, agenda, attendance, minutes, decisions, assignments, effectiveness and approval remain open. |
| Reports & Analytics | 5 | Several named analytics views use the generic report-export register. That is not the corresponding analysis. Audit performance also exposed the intermittent transport failure described above. |

The follow-up implements common register-state isolation, compact empty states, optional personal to-dos and bounded safe-read recovery at the gateway. It separately connects Change Control creation/register to governed projects, seeds MOPM change gates and requires retained Authority correspondence for approved submission/acceptance decisions. It does not close the specialist workflow gaps above.

Evidence is local and ignored: `.artifacts/live-register-review.json`, `.artifacts/live-register-01.png` through `43.png`, and `.artifacts/live-register-sheet-01.png` through `11.png`. The release verification log records subsequent checks and distinguishes first-pass captures from the published result.

A subsequent pass on the published follow-up waited for the correct title/view and completed loading before capturing each page. All 43 destinations completed without register warnings or HTTP/page failures. Its evidence is `.artifacts/live-register-review-settled.json`, `live-settled-register-01.png` through `43.png`, and `live-settled-sheet-01.png` through `11.png`; all contact sheets were visually inspected. The settled images then exposed a shared flex rule still stretching empty-state cards, which is corrected separately. Successful loading does not close the functional gaps in this table.
