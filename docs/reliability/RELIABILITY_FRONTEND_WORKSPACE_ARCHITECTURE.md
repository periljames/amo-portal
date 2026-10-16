# Reliability frontend: functional workspace architecture

## Why the old presentation was unsuitable

The old Reliability root rendered nearly every analytical chart, its formula
catalog, approval and effectivity controls, calculation snapshots, and source
registers in a single vertical page. Source management also put forms above
large evidence tables. This made comparison, daily data review, investigation
and report preparation unnecessarily scroll intensive.

## Routed workspaces delivered on PR #565

The shared \`ReliabilityModuleShell\` provides navigation consistently for
every Reliability route, including formal reporting and OCTM. It does not add
a competing authorization system or replace the operational APIs.

- **Overview** (\`/reliability\`): controlled KPI summary, period provenance,
  shortcuts, and a single prominent fleet trend, rather than 25+ charts.
- **Fleet / Network / Components / Oil / Engines / Deferrals / FRACAS /
  Source health** (\`/analytics/<category>\`): separate interactive chart
  canvases with existing time brushes, EHM metric controls, chart data,
  full-screen view, SVG/CSV export and underlying source drill-downs.
- **Analytical evidence** (\`/analytics/evidence\`): searchable, sortable
  aircraft comparison matrix and searched, paged source records. A
  200-record backend drill-down is clearly labeled as a *partial* result
  when the backend reports additional matching records.
- **Formulae / Administration / Governance / Calculation snapshots**:
  independent routes. Chart formula links lead to the dedicated library,
  not a missing in-page anchor.
- **Operational source control** (\`/operations/<task>\`): deep-linkable
  Flight Ops, deferred defects, component shop, SMS, QMS and workbook
  workflows. Expansive creation forms are collapsed until needed.
  Operational evidence tables use 25/50/100-row *client-side pages*.
- **Workbook data**: data registers, statistical alerts, mapping, workbook
  intake, CSV staging, report layouts and management report workflows have
  their own task routes.
- **Formal reporting**: report composition remains governed; its creation
  form is collapsible. Reporting obligations, AMP change recommendations
  and publication/distribution have separate navigation targets.
- **OCTM**: lands on 40 ± 10 FH engine-trend visualization instead of a
  long data-entry form, and has dedicated URLs for page entry, sector entry,
  register, verification, daily coverage and manufacturer profiles.
  Trend plot is capped at 180 recent complete intervals; detailed
  interval list paginates 25/50/100 rows.

## Data-volume guarantees and limitations

This PR improves rendering and usable client-visible pagination **within
the records already returned** by existing endpoints. It does not claim
that arbitrary millions of database rows are loaded or paged server-side
across every existing operational endpoint. Full historical pagination,
query-side sorting/filtering, asynchronous exports and genuine virtualization
are future API/data-grid improvements and should use tenant-scoped
cursor/keyset pagination. The OCTM entry and verification queue already
have offset-based backend pagination.

No chart creates new analytical claims, substitutes missing exposure
denominators, or bypasses QMS, CAMO, Safety, DMS, Procurement or formal
report publication controls.

## Acceptance checks

1. Open \`/maintenance/<tenant>/reliability\`; only summary KPIs and fleet
   trend are rendered initially.
2. Open every chart route and verify its toolbar, graph, full-screen,
   drill-down and Excel-safe exports.
3. Verify 25/50/100-row paging and filter resets in analytical,
   operational, workbook and OCTM tables.
4. Test browser Back/Forward, direct links, refresh, and tenant navigation.
5. Test Source Control mutations, independent OCTM review, FRACAS,
   formal reporting, and source-document workflows still use existing APIs.
6. Check responsive canvas/rail and keyboard navigation.
7. Confirm Reliability frontend lint/build/browser acceptance and other
   required repository jobs on the exact PR commit.

Passing source review alone is not production UI/UX acceptance. Browser
and operator validation with a large representative dataset is still needed.
