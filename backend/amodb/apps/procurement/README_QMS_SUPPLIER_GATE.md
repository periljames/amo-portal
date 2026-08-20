# QMS supplier usage gate

`assert_supplier_usage_allowed` is the cross-module backend gate used before a supplier becomes operationally usable. It composes the existing supplier lifecycle/scope/Quality-hold checks with the External Provider mandatory-contract rule. Operational entry points must not bypass it.
