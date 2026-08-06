# Reporting lines and display titles

## Purpose

The organization model must describe how work is supervised without turning job labels into access or aviation authority. A tenant may need any number of practical levels, for example:

`Maintenance Manager → Supervisor → Chief Crew → Engineer → Technician → Intern`

The hierarchy is therefore position-based and recursive. It is not limited to a fixed set of titles or a fixed number of levels.

## Controlled records

### Canonical position

The organization position is the approved corporate record. It contains the canonical title, organization unit, reporting position, approved headcount, supervisory status and any regulatory-post requirements.

Changing a canonical position may update the default title shown for occupants who have no approved title preference. It does not change a portal role, capability, group membership, competence record, licence or maintenance authorisation.

### Position assignment

The assignment identifies the person occupying the position, the actual reporting manager, effective dates, assignment type and any regulatory appointment evidence.

The reporting manager normally comes from the person occupying the direct parent position. The guided assignment workflow:

1. proposes the single occupant of the direct parent position;
2. requires the administrator or manager to choose when the parent has several occupants;
3. falls back to an occupied ancestor when appropriate; and
4. requires a documented matrix-reporting exception when the selected manager is outside the position chain.

Circular position and person-to-person reporting chains are rejected.

### Display title

A display title is a user-facing working label. It may be set during assignment or requested by the user, for example:

- canonical position: `Engineer`;
- approved display title: `Line Maintenance Engineer`.

A self-service request is reviewed by a manager with scope over the organization unit or by a tenant administrator. Approval updates presentation only. The canonical position remains visible for governance and audit purposes.

### Authorization boundary

The following remain independent of canonical and display titles:

- portal account role;
- capability assignments;
- user-group policies and segregation-of-duties controls;
- training and competence status;
- licences and credentials;
- maintenance authorisation scope;
- certifying-staff and CRS privileges;
- regulatory appointment and authority-acceptance evidence.

No title or reporting-line endpoint writes to those authorization records.

## Management scope

Tenant administrators use the elevated administration surface and may manage all tenant organization units.

Department or unit managers use the authenticated manager surface. Their editable scope is derived from:

- accountable manager, unit manager or deputy manager designation; or
- an active primary assignment to a supervisory position.

Their scope includes descendant organization units. They cannot use the manager surface to alter regulatory or authority-accepted positions. Those records stay under tenant-administrator control.

## User experience

The reporting-line builder provides:

- a compact hierarchy table with indented levels;
- a multi-level chain wizard;
- one-step person assignment with proposed reporting manager;
- canonical and display titles shown together;
- headcount and vacancy controls;
- preferred-title approval queue; and
- an explicit authorization-boundary notice.

Users can request or clear a preferred display title from **My Organization Profile**. Managers can open **Manage Reporting Lines** from **My Team**.
