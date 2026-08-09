# Incident Response

## Purpose

This runbook governs Platform Operations incidents recorded in the persistent incident center. It defines operator workflow and evidence requirements. It does not replace aviation occurrence reporting, emergency response, cybersecurity notification law, or tenant-specific contractual procedures.

## Lifecycle

The controlled incident lifecycle is:

`OPEN -> ACKNOWLEDGED -> INVESTIGATING -> MITIGATED -> RESOLVED`

Transitions advance one state at a time. Regressing to an earlier state or skipping a state is rejected by the API. Legacy `DETECTED` records are treated as `OPEN` during transition handling so historical data can move into the controlled lifecycle.

### OPEN

An incident has been created from an alert, operator observation, support escalation, change failure or other operational signal. Record a concise title, severity, source, affected components/nodes/tenants, alert/change references, runbook reference and external reference where applicable.

### ACKNOWLEDGED

A named Superadmin has accepted responsibility for coordinating the incident. Acknowledgement is not mitigation and must not be used to suppress investigation.

### INVESTIGATING

The team is actively collecting evidence, identifying scope and testing hypotheses. Record timeline events and links/references to relevant alerts, changes, nodes and tenants. Preserve uncertainty; do not state a root cause before evidence supports it.

### MITIGATED

Immediate user/platform impact is controlled or materially reduced. Continue monitoring long enough to prove the mitigation is stable. Mitigation may be rollback, failover, traffic reduction, worker pause, configuration reversal or another controlled action.

### RESOLVED

Service/operation is restored and the incident can leave active response. Resolution requires a timeline that explains what happened, what changed, what evidence confirms recovery and what follow-up work remains.

## Severity

The API accepts `INFO`, `LOW`, `MEDIUM`, `HIGH`, and `CRITICAL`. Severity should reflect actual/credible operational impact, not operator urgency alone. Escalate when new evidence shows larger tenant, security, data-integrity, regulatory or availability impact.

## Initial response procedure

1. Confirm whether the signal is current or stale observability data.
2. Identify REAL versus DEMO context before acting on tenant-scoped data.
3. Check recent deployment/configuration/feature-flag/maintenance/change markers.
4. Check SLO windows and burn rate, node/DB/queue health and affected routes.
5. Determine whether ordinary tenant traffic is affected or only the observability/control plane is degraded.
6. Open or update the incident with evidence and scope.
7. Acknowledge ownership and move to INVESTIGATING when active analysis begins.
8. Use reversible, least-destructive mitigation first.
9. Record every consequential control-plane action and its result.
10. Move through MITIGATED to RESOLVED only after recovery evidence exists.

## Observability outage rule

Prometheus, OTel, Grafana, Alertmanager or the Operations Gateway may fail independently. Such a failure is an observability/control-plane incident unless tenant evidence also shows business-service impact. Never declare the tenant API down solely because telemetry is unavailable.

When telemetry is stale, use application health checks, database evidence, tenant-facing synthetic probes and infrastructure access appropriate to the deployment. Mark conclusions that rely on partial evidence.

## SLO burn guidance

The repository currently evaluates 5m, 1h and 6h SLO windows. Fast-burn policy is triggered when 5m burn is at least 14.4 and 1h burn is at least 6.0. Sustained-burn policy is triggered when 1h burn is at least 2.0 and 6h burn is at least 1.0. These are operating signals; the incident severity still depends on scope and impact.

## Changes during an incident

Every deployment, migration, configuration change, feature-flag change or maintenance action relevant to an incident should have a Platform change marker/reference. Emergency actions still require an operator reason and audit evidence. High-risk durable commands retain their separate approval boundary unless an explicitly approved emergency procedure says otherwise.

## Evidence to retain

- incident timeline events and state-transition actors/timestamps;
- relevant alert references and SLO snapshots;
- node/database/queue/service health evidence;
- affected tenant IDs when necessary for operations evidence (not Prometheus labels);
- change/deployment references;
- command job IDs, dry-run output and final result;
- support/security references where relevant;
- recovery verification and follow-up issue/PR references.

## Post-incident review

For HIGH/CRITICAL incidents, document the causal chain supported by evidence, detection quality, time to acknowledge/investigate/mitigate/resolve, tenant impact, data-integrity impact, contributing changes, failed safeguards and follow-up owners. Add regression tests or alert/runbook changes for repeatable failure modes.

## Automation boundary

The repository provides persistent incident records and alerting rules, but automatic Alertmanager-to-incident creation must not be assumed unless the deployed integration is explicitly configured and tested. If an alert is only visible in Alertmanager/Grafana, an operator may still need to create/link the incident record.

## Acceptance

Production incident readiness requires a controlled exercise that demonstrates alert detection, incident lifecycle progression, a mitigation, recovery evidence, change correlation and observability-outage isolation while ordinary tenant traffic remains operational.
