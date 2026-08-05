# Corporate Structure and Personnel Governance

## Purpose

This domain separates six records that must not be collapsed into a single portal role:

1. **Organization unit** — where corporate accountability sits.
2. **Approved position** — the job, headcount, reporting position and any regulatory responsibility.
3. **Position assignment** — the person occupying that position, the effective period and reporting manager.
4. **Workforce engagement** — employee, fixed-term, intern, trainee, contractor, consultant, apprentice, volunteer or secondment terms.
5. **Group policy** — scoped access policy, approval chain, inheritance and segregation-of-duties tags.
6. **Personnel evidence** — identity verification, competence status, training currency, licences, authorisations and controlled acknowledgements.

A login account or access role is not proof of appointment, competence, regulatory acceptance or authority to certify maintenance.

## Implemented controls

### Corporate hierarchy

- Tenant-scoped organization units with parent-child hierarchy.
- Unit types for company, division, directorate, department, section, team, station, base and project.
- Accountable manager, manager, deputy manager and quality owner assignments.
- Parent-cycle prevention.
- Department and base mappings without replacing the existing operational department/base authorities.
- Effective dates, active status, cost centre, purpose and optional headcount ceiling.

### Position control

- Approved position register under organization units.
- Reporting-position hierarchy with cycle prevention.
- Headcount limits and vacancy calculations.
- Job family, grade, employment category, competence summary and responsibility statement.
- Regulatory-post flag, post type, appointment reference and authority-acceptance evidence requirements.
- Succession criticality.

### Person-to-position assignment

- Effective-dated primary and secondary assignments.
- Substantive, acting, secondment, temporary, interim, internship, apprenticeship and contract assignment types.
- Reporting manager and matrix-reporting exception evidence.
- Circular management-chain prevention.
- One active primary assignment per person.
- Approved-position headcount enforcement.
- Inactive users cannot receive active assignments.
- Regulatory positions require appointment evidence and, where configured, authority-acceptance evidence.

### Workforce engagement

- Permanent employee and time-bound contingent categories.
- Interns, trainees, apprentices, contractors, consultants, volunteers, temporary staff and seconded staff require an end date and responsible internal sponsor.
- Programme, institution/vendor, work-permit status, background-check status and access-expiry metadata.
- Controlled offboarding flag.
- One active engagement per person.

### Group policy

- User group linked to organization scope.
- Unit-only, unit-and-descendants or tenant-wide inheritance.
- Manual, position-driven or unit-driven membership mode.
- Manager and quality approval requirements.
- Explicit permission-template JSON and segregation-of-duties tags.
- Maximum assignment duration.

### Personnel profile and evidence

- Identity-verification status and evidence reference.
- Emergency contact.
- Data classification and retention class.
- Confidentiality, code-of-conduct and conflict-declaration acknowledgements.
- Competence, training, authorisation and medical-fitness **status only**. The portal must not store diagnoses or unnecessary medical detail.
- Review dates, restrictions and controlled notes.
- Multiple credentials for licences, authorisations, competence, training, medical status and certificates.
- Authority, scope, issue date, expiry, evidence-document reference and verifier trail.

## Portal surfaces

### Administration: `/admin/organization`

- Organization health metrics.
- Organization units and management hierarchy.
- Approved positions and vacancies.
- Personnel assignments.
- Employment and contingent engagements.
- Group policies.
- Compliance-gap queue.

### Personnel governance: `/admin/users/:id/governance`

- Identity and emergency profile.
- Corporate assignment and engagement history.
- Competence, training, authorisation and medical-status controls.
- Ethics/privacy acknowledgements.
- Credentials and expiry evidence.
- Readiness score and explicit gaps.

### Manager portal: `/manager/team`

- Direct reports only.
- Position, unit, engagement type and end date.
- Competence/training status, credential-expiry count and readiness gaps.
- Read-only by design. Management hierarchy does not automatically confer HR, quality or access-administration permissions.

### Employee self-service: `/my-profile`

- Signed-in person's corporate assignment, reporting manager, engagement terms, status and credentials.
- Read-only controlled data. Corrections follow manager/administrator workflows instead of silent self-editing.

## Regulatory and standards alignment intent

This implementation supplies structured, effective-dated and auditable records that can support an organisation's procedures and evidence. It does **not** by itself establish regulatory approval, ISO certification or legal compliance.

The control design is informed by:

- EASA Part-145 personnel and management-structure requirements, including accountable management, nominated management functions, competence assessment and controlled personnel authorisations.
- Kenya Civil Aviation requirements and KCAA AMO certification/oversight expectations for approved organisation structure, management personnel, manuals, competence and records.
- ISO 9001 concepts for organizational roles, competence, awareness and documented information.
- ISO/IEC 27001 identity, access lifecycle, least privilege and segregation-of-duties controls.
- ISO 30414:2025 human-capital reporting areas, including workforce composition, leadership, compliance, mobility, turnover, skills and development.
- ISO 45001 role clarity, competence and worker participation concepts.

The organisation's approved manuals, exposition, regulatory approvals, local employment law, privacy obligations and authority-specific forms remain authoritative.

## Next controlled increments

1. Approval workflow objects for organization changes, appointments, acting assignments and group-policy grants.
2. Versioned organization charts with proposed/effective/superseded states.
3. Position descriptions and competence matrices linked to training requirements.
4. Succession planning and deputy/acting coverage alerts for critical posts.
5. Automated access provisioning from approved position/group policies, with explicit human approval and rollback.
6. Offboarding orchestration across accounts, base assignments, authorisations, equipment, records and external integrations.
7. Human-capital reporting with privacy-safe aggregation and auditable definitions.
8. Authority-form and MOE cross-reference registers for nominated personnel and accepted management changes.
