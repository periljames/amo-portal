# Tenant Health Model

## Purpose

Tenant Health is a Superadmin operating signal for prioritising investigation across a large tenant fleet. It is not an aviation safety, airworthiness, regulatory-compliance, or contractual service-level determination.

The authoritative implementation is `tenant_health()` in `backend/amodb/apps/platform/ops_logic.py`, with additional fleet-risk penalties applied in `backend/amodb/apps/platform/ops_scale_router.py`.

## Base score

A tenant starts at `100.0`. The base model applies these deductions:

| Condition | Deduction |
| --- | ---: |
| Tenant inactive | 60 |
| Tenant read-only | 20 |
| API error+timeout rate >= 5% | 30 |
| API error+timeout rate >= 1% and < 5% | 15 |
| Quota utilisation >= 95% | 25 |
| Quota utilisation >= 80% and < 95% | 10 |
| Last route telemetry older than one hour | 10 |

The API error rate is `(server errors + timeouts) / request count`; when the denominator is zero the ratio is zero rather than undefined. The base score is clamped to `[0, 100]`.

Base status bands are:

- `CRITICAL`: score < 50
- `WARN`: score < 80
- `HEALTHY`: score >= 80

The base payload also includes the calculated error rate and human-readable reasons for deductions.

## Fleet risk overlay

The server-side Tenant Fleet adds operational risk penalties to the base score:

| Risk | Deduction |
| --- | ---: |
| At least one overdue invoice | 20 |
| At least one open HIGH/CRITICAL security alert | 20 |
| Integration failure count > 0 | 10 |
| At least one open/new/pending support ticket | 5 |

After the overlay, the score is floored at zero and the same status bands are recalculated.

The overlay also exposes explicit risk fields instead of forcing clients to infer them: lifecycle, plan, licence state, read-only state, modules, user counts, asset count, 24-hour request activity, P95 latency, quota/storage context, billing risk, security risk, integration failure and support state.

## Data inputs

Current server-side Fleet construction uses authoritative application records including:

- tenant `is_active` and `is_demo` state;
- latest tenant licence/catalogue SKU;
- module subscriptions;
- user and active-user counts;
- active aircraft count;
- pending overdue invoices;
- open HIGH/CRITICAL platform security alerts;
- support ticket state;
- webhook/integration failure counts;
- recent route-metric rollups;
- latest tenant resource snapshot.

Missing data is not silently converted into a positive proof. For example, a missing resource snapshot leaves quota/storage fields unavailable.

## REAL / DEMO isolation

Tenant Fleet/360 must select tenants using the authoritative tenant `is_demo` field. `REAL` and `DEMO` are mutually exclusive operating contexts. A Tenant 360 request whose tenant environment does not match the requested mode returns not found rather than crossing environments.

## Fleet filtering and pagination

`GET /ops/v1/tenant-fleet` supports server-side filters for:

- search text;
- health;
- active state;
- country;
- plan;
- module;
- lifecycle;
- billing risk;
- security risk;
- integration state;
- support state;
- recent activity window;
- minimum/maximum users;
- minimum/maximum assets.

Supported sorts include health, name, traffic, users, assets and activity. Pagination is cursor based. The cursor is bound to a fingerprint of the active filter set; reusing a cursor with changed filters is rejected.

## Tenant 360

`GET /ops/v1/tenant-360/{tenant_id}` assembles the investigation surface into explicit sections: Overview, Health, Usage, Users, Modules, Subscription, Billing, Performance, Integrations, Jobs, Support, Security, Audit and Changes.

## Interpretation rules

1. Health is a prioritisation score, not a root-cause diagnosis.
2. Operators should use the reason/risk fields and Tenant 360 evidence before acting.
3. A low-traffic tenant must not be labelled healthy solely because no errors were observed; activity/freshness should be considered separately.
4. Commercial, security and support penalties are intentionally visible so a score can be explained.
5. Threshold changes are behavioural changes and require tests, release notes/change markers, and review of saved-view/operator expectations.

## Validation expectations

CI should cover score boundaries, risk overlays, REAL/DEMO separation, cursor invalidation, the complete filter matrix and representative 1,000-tenant pagination. Production acceptance additionally requires a populated Fleet demonstration using representative tenant data.
