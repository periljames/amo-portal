# KCAA Reliability Profile

**Verified against official KCAA web material:** 2026-08-07

## Current-source control

Official sources used by the baseline profile:

- Kenya Civil Aviation Regulations 2025 publication/transition page: https://www.kcaa.or.ke/legislation-publications/regulations-2025
- KCAA Airworthiness Advisory Circular list: https://www.kcaa.or.ke/legislation-publications/advisory-circulars
- `CAA-AC-AWS010D — Reliability Programme`, Rev D/effective 01 July 2018, as currently listed by KCAA.

KCAA states that the revised 2025 regulations are binding and affected operators must review requirements and align/revise controlled manuals/programmes where necessary. The 2018 circular remains useful Reliability advisory material but was issued against the prior regulatory framework.

Therefore AMO Portal does **not** treat `CAA-AC-AWS010D` by itself as proof of current KCARs 2025 compliance.

## Baseline gate

`KCAA-CURRENT-REGULATORY-MAPPING` is seeded as:

- mandatory;
- applicable by default;
- `GAP` by default;
- publication blocking;
- manual current-reference verification required.

A tenant must record the exact current KCARs 2025 / authority / accepted Reliability Programme basis that applies to its operation. No current paragraph number is invented when it has not been independently verified.

## Legacy/advisory mapping retained

The current baseline captures `CAA-AC-AWS010D` guidance for:

- fleet composition/status;
- operating days/utilisation/FH/FC/landings as applicable;
- average utilisation and flight duration;
- technical delays/cancellations and trends;
- diversions and significant operational interruptions;
- engine/propeller related events where applicable;
- MEL/deferral trends;
- long-term trend presentation;
- alert/statistical methods;
- investigation/corrective action;
- reporting/distribution/retention.

These are analytical/reporting expectations and remain subject to the tenant's current approved programme and 2025 regulatory mapping.

## Profile behaviour

- Profile code: `KCAA`
- Baseline version: `2026-08-07.1`
- Historical windows configured: 12, 24 and 36 months.
- Missing denominators are withheld, never reported as zero reliability.
- Mandatory unresolved current-regulation mapping blocks approval/publication.
- A Reliability-driven AMP recommendation remains a recommendation until the applicable technical/quality/authority approval path is complete.

## Known regulatory gap

The exact tenant-applicable KCARs 2025 airworthiness paragraph/reference and any operator-specific KCAA approval/acceptance conditions must be captured as controlled requirement revisions before a KCAA-profile publication is represented as complete. This is intentionally visible as a system gap rather than silently inferred from the 2018 circular.
