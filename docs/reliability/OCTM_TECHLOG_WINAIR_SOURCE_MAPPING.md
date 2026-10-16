# Source-document mapping — OCTM, SL/MCM/1, SL/MCM/1B and WinAir

Source-review basis (16 October 2026):
- \`OCTM(1).xlsm\`: 23 sheets, aircraft-named tabs, engine monitoring and stores entries.
- \`Oil Consumption.xlsx\`: two fleet-family worksheets, \`DHC 8 \` and \`C208B\`, tracking technical-sheet oil entries alongside WinAir oil requisitions.
- \`SLMCM1 - Aircraft Technical Logbook.pdf\`: form **SL/MCM/1, Issue 01 Rev. 03, 09 Mar 2023**.
- \`SLMCM1B-ACCEPTABLE DEFERRED DEFECTS.pdf\`: form **SL/MCM/1B, Issue 01 Rev. 01, 01 Dec 2019**.

The forms and historical worksheets are source examples, **not** confirmation
of currently approved procedures, valid OEM limits, source-file correctness,
or a signoff to apply old engine metadata today.

## Authoritative source classification

| Source element | Actual scope | Target OCTM handling |
| --- | --- | --- |
| SL/MCM/1: leg FROM/TO, takeoff/landing, Airtime, Flight Time | Up to 9 legs per **page** | Preserve each leg; only summed **Flight Time** becomes the page utilization for each installed engine after reconciliation |
| SL/MCM/1: Engine Oil **Level** L/H and R/H | Per leg | Preserve in page source-context as a **level**, never reclassify as oil quantity added |
| SL/MCM/1: **OIL Added** L/H, R/H, APU | Page total | One OCTM candidate per installed aircraft engine, marked \`TECHLOG_PAGE\`; APU is retained as context but **excluded** from engine consumption |
| SL/MCM/1: TTAF brought forward/updated, TCSN brought forward/updated | Aircraft totals | Compare TTAF movement to page Flight Time; do **not** treat TTAF as engine ETSN |
| SL/MCM/1: defect, rectification, work card, signature & authority, CRS | Aircraft maintenance/technical-record evidence | Keep Technical Records authoritative; store identifiers for traceability, never infer a CRS or maintenance completion from page import |
| SL/MCM/1B: ADD number, defect verbatim, MEL reference/category, limitation, raised by, clearance, sign/auth/date | Deferred defect / continuing airworthiness | Link to authoritative deferred-defect and defect/FRACAS records; do not copy dispatch/MEL rules into Reliability |
| OCTM(1).xlsm: date, techsheet, engine ETSN, utilization, oil uplift, calculated OCR | Engine monitoring / historical workbook | Import only source-observable fields through mapped staging + review; **discard cached OCR formula values as authoritative data** |
| OCTM(1).xlsm: engine serial, position, build spec, installation date, EMM ref/revision/limit | Mixed reference/header metadata | Cross-check against *date-effective* component installation and current technical data before approval |
| OCTM(1).xlsm and Oil Consumption.xlsx: technical log uplifts versus **WinAir requisitions**, task number, quantity issued and variance | Inventory / source reconciliation | Treat stores issues/returns as separate stock movements linked by task/part/date/aircraft; never infer consumption from an issue |
| Oil Consumption.xlsx: Maintenance, No Uplift, Not Requested, Engine Change | Exception/context labels | Maintain separate exception reasons; do not count maintenance refills or engine change inventory as routine engine oil consumption |

## Confirmed workbook issues that prevent blind import

1. \`OCTM(1).xlsm\` contains current engine serial metadata not aligned with
   older worksheet column headings. For example the 5Y-SLC reference panel
   includes \`PCE-124509\` whereas the ENG 2 table heading shows
   \`PCE-123260\`; 5Y-SLK also shows differing current reference and
   historical column engine serials. Engine *date-specific installation
   intervals* must be mapped from authoritative aircraft component records.
2. Blank/calculated regions in multiple aircraft sheets contain
   \`#DIV/0!\` values. An error cell is **not** a valid observed OCR or
   a confirmed zero. Import staged *raw* quantities and cumulative counters,
   with source worksheet, row and cell provenance.
3. Workbook display limits include about 0.270 qt/FH for some PW123
   records, 0.143 for PW121 and 0.095 for PT6A-114A, but these are
   only **claims made in the historical workbook**, not approved OEM
   limit configuration. Verify technical-data revision, engine model,
   applicability, units and effective dates before permitting approval.
4. The C208B \`Oil Consumption.xlsx\` worksheet includes WinAir issues
   on days marked \`No Uplift\`, \`Maintenance\` and \`Engine Change\`.
   A row-matched issue-minus-uplift is only a reconciliation *exception*,
   not necessarily loss or misuse: returns, inventory balance, delays,
   maintenance consumption and period cut-off must be considered.
5. The DHC 8 workbook includes grouped subtotal/variance rows and date
   serials. These are **not** technical-log oil events and must be
   filtered in a future controlled import.

## Data-entry implementation on PR #565

- **Sector entry:** retained for sources explicitly recording oil quantities
  against one individual sector.
- **Techlog page:** the new \`Techlog page\` tab copies the PDF source
  structure, including a 1–9-leg grid, per-leg oil **levels**, page Flight
  Time and TTAF, per-page L/H and R/H oil **added**, optional APU oil,
  maintenance-release reference and defect/ADD link references.
  Preview precedes atomic creation of 1 or 2 **draft** engine observations.
  A blank oil-added field is recorded as \`MISSING\`, not \`CHECK_ZERO\`.
- \`source_scope\` is persisted with every entry. Page/sector inputs for
  the same engine/date cannot be independently approved in conflict; the
  calculation also withholds a potentially doubled source date.
- A page cannot invent engine ETSN: only an engine-specific source may
  supply \`engine_counter_hours\`. Page TTAF and TCSN remain in source context.
- Leg hours must sum to the page Flight Time within 0.02 FH. Where provided,
  TTAF brought forward + flight time must match updated TTAF within
  the same tolerance. This catches transcription mistakes but cannot
  independently prove accuracy of the paper page.
- Source data is tenant-scoped, requires \`reliability.ingest\`, rejects
  duplicate entries atomically, and remains subject to the existing
  independent Reliability verification queue.

## Deliberately not implemented as a second repository

The WinAir worksheet calls for a **Stores/Procurement-source reconciliation
view**, not a new independent stock-issue ledger inside Reliability.
Once the canonical requisitions/receipts/issues/returns and oil part codes
are identified, join the authoritative movements to the aircraft/page,
task, dates, original units and servicing purpose. Preserve discrepancies
with reason, owner, review and closure; do not quietly force balances to zero.

SL/MCM/1B must link to the existing deferred-defect record with its
limitation, MEL basis and clearance authority, not be recreated as an OCTM
dispatch approval. No source in these files authorizes changing MEL
conditions or allowing operation beyond a limitation.

Outstanding for production: confirm effective installation histories,
source-document upload/scan binding in DMS, full Tech Records completeness,
Avi Pro native data contract, authentic WinAir transaction adapter and
reconciliation, and approved OEM limits. The uploaded workbooks are not
silently bulk-imported by this change.
