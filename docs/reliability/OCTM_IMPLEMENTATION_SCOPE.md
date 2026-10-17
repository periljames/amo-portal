# Governed Oil Consumption Monitoring (OCTM)

## Scope of this change

This implementation adds a distinct OCTM workspace under
\`/maintenance/:amoCode/reliability/octm\`, backed by the existing
tenant-scoped Reliability authorization system.

The baseline is the supplied OCTM design brief referring to MCM Issue 3,
Revision 11 §3.10.6.14 (40 ± 10 flight hours), §3.10.2.3 (Reliability
review), and EFB Manual §§3.2.1.4–3.2.1.5. The code does **not**
claim manufacturer limits or Avi Pro vendor interfaces have been verified.

### Live implemented functionality

- Register one oil observation per engine, techsheet and event sequence.
- Distinguish TOP_UP, CHECK_ZERO, MISSING, NO_OPERATION, OIL_CHANGE,
  MAINTENANCE_REFILL and LEAK_SERVICING. Unrecorded is never assumed zero.
- Record aircraft, physical engine serial number, installation reference,
  sector, event date, servicing context, original quantity/unit, reference
  level/method, flight hours and maintenance-completion status.
- Keep source entries in DRAFT until a user with
  \`reliability.data_quality.resolve\` verifies them; maintenance information
  must be confirmed complete. Duplicate source keys return existing data
  only if all values agree; conflicts require review.
- Corrections preserve before/after values, reason and actor, invalidate
  verification and require re-review. Review, correction and profile
  actions also produce existing Reliability audit-chain events.
- Materialize **no** user-supplied rate as a verified calculation. Monitoring
  is computed by the server from verified sources. Flight hours and oil
  added must belong to the same physical engine/installation and source
  sequence. Calculation uses disjoint intervals with a target of 40 FH.
  Windows exceeding 50 FH withhold the rate. Missing entries,
  non-routine servicing and changes of oil-reference conditions break the
  continuity chain.
- Use volume units QT/L/US_GAL only; mass-to-volume conversion is not
  assumed. Original units are retained.
- Create versioned, evidenced manufacturer limit profiles with a
  distinct second-person approval control. **No preloaded numeric limits**.
- Plot interval consumption alongside approved and effective manufacturer
  limits; distinguish OEM-limit exceedances from configured trend alerts.

## Daily personnel workflow and enforced safeguards

1. Select an **existing registered aircraft** (including historical/inactive
   aircraft when entering old source records). Never create an OCTM event
   against an unregistered or foreign-tenant aircraft.
2. Inspect the physical technical-log/engine-installation history. A prior
   engine serial and installation reference is offered only as a **hint**.
   Record the actual physical engine serial, position, installation reference,
   operating date, techsheet, sector and within-techsheet event sequence.
3. Choose exactly what the source establishes: TOP_UP, CHECK_ZERO, MISSING,
   NO_OPERATION or a separately identified nonroutine maintenance service.
   The interface does not equate an empty oil field with a zero uplift.
   Preserve original units and oil specification; quantity fields reject
   non-finite/negative figures. Records with flight-hour exposure must
   identify a sector to prevent duplicate exposure.
4. Register and identify the actual source evidence in Tech Records/DMS.
   Include maintenance-completion status; crew-only EFB closure must
   **not** be represented as maintenance completion.
5. Save an incomplete draft if source information is outstanding. The
   inline verification checklist identifies incomplete requirements.
   Authoritative monitoring calculations exclude draft/returned records.
6. An independent, capability-authorized reviewer sees server-derived
   readiness findings before verification and must explicitly confirm
   original source, physical engine/installation and sector-flight-hour
   exposure. Creator or latest correction actor cannot verify their own
   submission. A returned entry must first be corrected.
7. Corrections retain the before/after record, actor and reason, invalidate
   the prior verified state and require another review. Correctors can
   inspect the history from the Source register. Concurrent duplicate
   submissions cannot silently create conflicting records.
8. The **Daily coverage** screen reconciles entered OCTM sector references
   with existing engine-flight snapshots. Unmatched sectors require follow-up
   but are explicitly **not definitive proof** of missing techsheets or flights.
   Missing snapshots are not interpreted as evidence that no aircraft flew.
9. Engine trend calculations group multiple servicing events on the same
   engine/sector and count their flight hours once; valid windows use
   consistent oil-reference conditions, installation and 40 ± 10 FH.
   Nonroutine service, missing data and reference changes reset the
   monitoring chain. Out-of-range windows withhold a formal rate.
10. Manufacturer limits require entered technical-data reference and revision,
    then review and signed attestation by another authorized person.
    The software does not authorize operation or continued dispatch.

**Historical source register:** Both unverified queue and complete record
listing have server-side pagination (200 rows per page); filters apply to
the loaded page. Correction history is available for source entries.

## Source-faithful SL/MCM/1 page capture

The extra supplied source samples are mapped in
`docs/reliability/OCTM_TECHLOG_WINAIR_SOURCE_MAPPING.md`.

The **Techlog page** screen accepts up to nine flight legs and preserves
their oil **levels** without falsely treating these readings as oil **added**.
L/H and R/H oil added appear on the source at page level, while APU servicing
is retained as context and excluded from engine OCTM calculations.

The workflow previews then creates page-linked, per-engine draft observations
in a single transaction. Entered Flight Time must reconcile with the original
page total and recorded TTAF movement, when present. Engine ETSN is **not**
inferred from aircraft TTAF. Page and sector sources cannot overlap in
verified records for one engine/date and are withheld defensively by
the calculation if earlier records contain such a conflict.

The **Correct page** action loads the whole source page, requires a reason,
retains before/after revision history for each engine, and reopens **all**
associated engine observations for independent verification, even when only
one engine's uplift amount changes.

Maintenance release, 24-hour checks, original defects and ADD numbers are
referenced for review; no technical-log certification, MEL approval or
deferred-defect clearance is issued by this OCTM workflow.

## Important boundaries and follow-on integration

- The workbook \`OCTM.xlsm\` has 23 worksheets and must be treated as a
  historical **source**, not authoritative formula output. This change
  does not upload/parse an XLSM file or migrate unverified formulas.
  Build a guarded raw-row import only after mapping sheet headers,
  aircraft registration and historical engine installations, validating
  individual techsheets, and arranging Reliability sign-off.
- Physical techsheet scans are referenced by the evidence-reference field.
  This change does **not** implement DMS binary upload or OCR processing.
- Source type values anticipate read-only Avi Pro exports or vendor API
  records; there is **no** claim of a connected or functioning vendor feed.
  Vendor interface documentation and representative actual exports are
  required for field mapping and reliable deduplication.
- Engine installation references currently come from operator-entered
  technical records. Cross-check against the authoritative historic
  component installation register before approving operational use.
- Daily **snapshot-to-OCTM** reconciliation is available. It is not a
  complete authoritative techsheet receipt register until linked to
  Flight Operations/Technical Records. Stores reconciliation, FRACAS
  investigation workflow links and signed quarterly report embedding
  remain separate integration steps, not deployed features of this PR.
- No software result authorizes dispatch or substitutes for current
  manufacturer maintenance instructions and required engineering action.
- For multiple sector/top-up events, count flight-hour exposure **once**
  for each segment, not once per oil top-up.

## Verification

Focused tests are in \`backend/amodb/apps/reliability/tests/test_octm.py\`.
Run database migrations and backend + frontend build/tests in CI against
the exact PR head. Do not merge on the strength of source inspection alone.
