# Training & Competence Module

## Information architecture

Top-level module route:
- `/maintenance/:amoCode/:department/training-competence`

Sub-pages/workspaces:
1. Overview
2. Training Matrix
3. Schedule
4. Sessions
5. Attendance
6. Assessments
7. Certificates
8. Personnel Records
9. Templates
10. Admin / Settings

The module uses a mobile-first one-column layout with drawer-based detail interactions.

## Route inventory

### Frontend
- `/maintenance/:amoCode/:department/training-competence`
- `/maintenance/:amoCode/:department/qms/training`
- `/maintenance/:amoCode/:department/qms/events`
- `/maintenance/:amoCode/:department/training`
- `/verify/certificate/:certificateNumber`

### Backend
- `GET /training/courses`
- `GET /training/requirements`
- `GET /training/events`
- `GET /training/events/{event_id}/participants`
- `PUT /training/event-participants/{participant_id}`
- `GET /training/records`
- `GET /training/deferrals`
- `POST /training/deferrals`
- `PUT /training/deferrals/{deferral_id}`
- `GET /training/certificates`
- `POST /training/certificates/issue/{record_id}`
- `GET /public/certificates/verify/{certificate_number}`

## Permission and entitlement model

- Training API remains gated by module entitlement (`require_module("training")`).
- Mutating actions use existing training editor guardrails (Quality/Admin role checks).
- Public certificate verification endpoint is intentionally exposed without auth and only returns safe fields.

## Certificate lifecycle (current implementation)

- Certificates are issued against an existing training record.
- Issuance stamps an immutable human-readable certificate number into `training_records.certificate_reference`.
- Re-issuing the same record is blocked to preserve immutability.
- Public verification resolves by certificate number and returns validity metadata.

## Known follow-up items

- Template-versioned PDF rendering with embedded QR/barcode artifact files.
- Revocation/supersession status history model.
- Rich assessment/question-bank workflow persistence.
