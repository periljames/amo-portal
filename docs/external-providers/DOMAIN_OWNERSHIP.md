# Domain ownership
| Responsibility | Existing authoritative owner | Extension rule |
|---|---|---|
| Supplier master | `procurement_suppliers` | Same tenant organization for all roles |
| Quality decisions | `supplier_governance_service` and QMS provider state transitions | No alternative decision engine |
| Approval scopes | `procurement_supplier_approval_scopes` | Existing Quality gate remains mandatory |
| Contracts | `quality_external_provider_contracts` | Link, do not copy contractual status |
| Evidence | `quality_external_provider_evidence` and DMS | Link exact controlled revisions |
| Provider roles/sites/contacts/capabilities | New `external_provider_*` tables | Descriptive only, nonauthoritative |
| Orders, requisitions, receipts | Procurement | Must retain `assert_supplier_usage_allowed` |
| Audit findings and CAR | QMS | Reference governed provider instead of duplicating CAR |
