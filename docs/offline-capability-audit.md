# Offline capability audit

Generated from registered API write routes and the frontend replay registry. Run `npm run audit:offline` in `frontend` to regenerate.

33 creation workflows automatically save offline through the shared JSON transport, in addition to the six existing guarded operations. New create handlers commit domain rows and replay receipts atomically. The audit verifies that every frontend creation contract has a matching registered server handler. The table identifies remaining operations without a replay contract; full offline functionality across all modules is not implemented.

Cached reads require a prior successful download. Fresh-every-time reads retain an encrypted offline copy. Live authority checks are excluded from stale fallback. QMS encrypted evidence and document downloads use separate explicit workflows.

| API module | Replay-enabled write routes | Explicitly online | No replay contract |
| --- | ---: | ---: | ---: |
| accounts | 0 | 10 | 72 |
| ai | 0 | 0 | 2 |
| aircraft_architecture | 0 | 5 | 29 |
| audit | 0 | 0 | 1 |
| bootstrap | 0 | 0 | 4 |
| crs | 0 | 1 | 2 |
| doc_control | 4 | 3 | 111 |
| finance | 1 | 0 | 5 |
| fleet | 1 | 6 | 20 |
| foundations | 0 | 3 | 8 |
| integrations | 0 | 0 | 3 |
| inventory | 6 | 0 | 0 |
| manuals | 0 | 2 | 29 |
| platform | 0 | 6 | 79 |
| procurement | 4 | 2 | 26 |
| quality | 2 | 34 | 231 |
| realtime | 0 | 1 | 17 |
| reliability | 6 | 9 | 114 |
| rostering | 2 | 11 | 45 |
| tasks | 1 | 0 | 2 |
| technical_records | 5 | 1 | 6 |
| training | 4 | 13 | 157 |
| work | 5 | 2 | 7 |
| workforce | 1 | 8 | 49 |

Cross-device updates require connection to the server. Local encrypted queues stay on the device where they were created. Conflicting revisions require review; they are not silently overwritten.

Browser automation tests actual Chrome offline storage, reload, unchanged replay keys, shared-tab leases and conflicting edits from isolated device profiles using fixture HTTP responses. It does not replace live PostgreSQL, permissions, evidence upload and production device acceptance testing.

This static audit does not test deployment connectivity or production end-to-end acceptance.
