// Reviewed creation workflows with atomic backend replay receipts.
export const OFFLINE_CREATE_ROUTES = [
  { id: "doc_control-create_change_request", module: "doc_control", path: "/doc-control/workspace/t/{tenant_slug}/change-requests", label: "document change request" },
  { id: "doc_control-create_review", module: "doc_control", path: "/doc-control/workspace/t/{tenant_slug}/reviews", label: "document review plan" },
  {
    "id": "training-create_course",
    "module": "training",
    "path": "/training/courses",
    "label": "create course"
  },
  {
    "id": "training-create_requirement",
    "module": "training",
    "path": "/training/requirements",
    "label": "create requirement"
  },
  {
    "id": "training-create_event",
    "module": "training",
    "path": "/training/events",
    "label": "create event"
  },
  {
    "id": "training-create_deferral_request",
    "module": "training",
    "path": "/training/deferrals",
    "label": "create deferral request"
  },
  {
    "id": "tasks-create_personal_task",
    "module": "tasks",
    "path": "/tasks/personal",
    "label": "create personal task"
  },
  {
    "id": "fleet-create_defect_report",
    "module": "fleet",
    "path": "/aircraft/{serial_number}/defects",
    "label": "create defect report"
  },
  {
    "id": "work-create_work_order",
    "module": "work",
    "path": "/work-orders",
    "label": "create work order"
  },
  {
    "id": "work-create_task",
    "module": "work",
    "path": "/work-orders/{work_order_id}/tasks",
    "label": "create task"
  },
  {
    "id": "work-create_work_log",
    "module": "work",
    "path": "/work-orders/tasks/{task_id}/work-logs",
    "label": "create work log"
  },
  {
    "id": "technical_records-create_utilisation",
    "module": "technical_records",
    "path": "/records/aircraft/{tail_id}/utilisation",
    "label": "create utilisation"
  },
  {
    "id": "technical_records-create_maintenance_record",
    "module": "technical_records",
    "path": "/records/maintenance-records",
    "label": "create maintenance record"
  },
  {
    "id": "technical_records-create_airworthiness_item",
    "module": "technical_records",
    "path": "/records/airworthiness/{item_type}",
    "label": "create airworthiness item"
  },
  {
    "id": "technical_records-create_watchlist",
    "module": "technical_records",
    "path": "/records/watchlists",
    "label": "create watchlist"
  },
  {
    "id": "technical_records-create_compliance_action",
    "module": "technical_records",
    "path": "/records/compliance-actions",
    "label": "create compliance action"
  },
  {
    "id": "inventory-receive_inventory",
    "module": "inventory",
    "path": "/inventory/receive",
    "label": "receive inventory"
  },
  {
    "id": "inventory-inspect_inventory",
    "module": "inventory",
    "path": "/inventory/inspect",
    "label": "inspect inventory"
  },
  {
    "id": "inventory-transfer_inventory",
    "module": "inventory",
    "path": "/inventory/transfer",
    "label": "transfer inventory"
  },
  {
    "id": "inventory-issue_inventory",
    "module": "inventory",
    "path": "/inventory/issue",
    "label": "issue inventory"
  },
  {
    "id": "inventory-return_inventory",
    "module": "inventory",
    "path": "/inventory/return",
    "label": "return inventory"
  },
  {
    "id": "inventory-scrap_inventory",
    "module": "inventory",
    "path": "/inventory/scrap",
    "label": "scrap inventory"
  },
  {
    "id": "finance-create_invoice",
    "module": "finance",
    "path": "/finance/invoices",
    "label": "create invoice"
  },
  {
    "id": "procurement-supplier_create",
    "module": "procurement",
    "path": "/api/maintenance/{amo_code}/procurement/suppliers",
    "label": "supplier create"
  },
  {
    "id": "procurement-requisition_create",
    "module": "procurement",
    "path": "/api/maintenance/{amo_code}/procurement/requisitions",
    "label": "requisition create"
  },
  {
    "id": "procurement-rfq_create",
    "module": "procurement",
    "path": "/api/maintenance/{amo_code}/procurement/rfqs",
    "label": "rfq create"
  },
  {
    "id": "procurement-quote_create",
    "module": "procurement",
    "path": "/api/maintenance/{amo_code}/procurement/quotes",
    "label": "quote create"
  },
  {
    "id": "reliability-create_recommendation",
    "module": "reliability",
    "path": "/reliability/recommendations",
    "label": "create recommendation"
  },
  {
    "id": "reliability-create_event",
    "module": "reliability",
    "path": "/reliability/events",
    "label": "create event"
  },
  {
    "id": "reliability-create_fracas_case",
    "module": "reliability",
    "path": "/reliability/fracas/cases",
    "label": "create fracas case"
  },
  {
    "id": "reliability-create_fracas_action",
    "module": "reliability",
    "path": "/reliability/fracas/actions",
    "label": "create fracas action"
  },
  {
    "id": "reliability-create_engine_snapshot",
    "module": "reliability",
    "path": "/reliability/engine-snapshots",
    "label": "create engine snapshot"
  },
  {
    "id": "reliability-create_oil_uplift",
    "module": "reliability",
    "path": "/reliability/oil-uplifts",
    "label": "create oil uplift"
  }
] as const;
