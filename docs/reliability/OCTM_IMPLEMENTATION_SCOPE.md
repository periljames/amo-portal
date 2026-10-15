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
- Daily completeness reconciliation, stores reconciliation, FRACAS
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
