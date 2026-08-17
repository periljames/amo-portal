from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from amodb.db_capacity import connection_budget, validate_connection_budget


class ConnectionBudgetTests(unittest.TestCase):
    def test_external_pool_budget_fits_inside_reserved_database_capacity(self) -> None:
        values = {
            "DB_EXTERNAL_POOLER": "true", "DB_MAX_CONNECTIONS": "300",
            "DB_ADMIN_CONNECTION_RESERVE": "20", "DB_MIGRATION_CONNECTION_RESERVE": "5",
            "PGBOUNCER_API_POOL_SIZE": "90", "PGBOUNCER_WORKFORCE_POOL_SIZE": "45",
            "PGBOUNCER_GENERAL_POOL_SIZE": "35", "PGBOUNCER_SCHEDULED_POOL_SIZE": "10",
            "PGBOUNCER_READ_POOL_SIZE": "30",
        }
        with patch.dict(os.environ, values, clear=False):
            budget = validate_connection_budget()
        self.assertTrue(budget.valid)
        self.assertEqual(budget.projected, 210)
        self.assertEqual(budget.usable, 275)

    def test_invalid_fleet_budget_fails_before_serving_traffic(self) -> None:
        with patch.dict(os.environ, {
            "DB_EXTERNAL_POOLER": "true", "DB_MAX_CONNECTIONS": "100",
            "DB_ADMIN_CONNECTION_RESERVE": "20", "DB_MIGRATION_CONNECTION_RESERVE": "5",
            "PGBOUNCER_API_POOL_SIZE": "90", "PGBOUNCER_WORKFORCE_POOL_SIZE": "45",
            "PGBOUNCER_GENERAL_POOL_SIZE": "35", "PGBOUNCER_SCHEDULED_POOL_SIZE": "10",
            "PGBOUNCER_READ_POOL_SIZE": "30",
        }, clear=False):
            self.assertFalse(connection_budget().valid)
            with self.assertRaises(RuntimeError):
                validate_connection_budget()

    def test_direct_pool_budget_counts_isolated_runtime_roles(self) -> None:
        values = {
            "DB_EXTERNAL_POOLER": "false",
            "DB_MAX_CONNECTIONS": "100",
            "DB_ADMIN_CONNECTION_RESERVE": "10",
            "DB_MIGRATION_CONNECTION_RESERVE": "5",
            "DB_POOL_SIZE": "10",
            "DB_MAX_OVERFLOW": "5",
            "PORTAL_API_PROCESS_COUNT": "1",
            "PORTAL_WORKER_PROCESS_COUNT": "5",
            "PORTAL_WORKER_DB_POOL_SIZE": "2",
            "PORTAL_WORKER_DB_MAX_OVERFLOW": "1",
            "PORTAL_SCHEDULED_PROCESS_COUNT": "1",
            "PORTAL_SCHEDULED_DB_POOL_SIZE": "2",
            "PORTAL_SCHEDULED_DB_MAX_OVERFLOW": "1",
            "DOCUMENT_EVIDENCE_PACK_PROCESS_COUNT": "1",
            "DOCUMENT_EVIDENCE_PACK_DB_POOL_SIZE": "1",
            "DOCUMENT_EVIDENCE_PACK_DB_MAX_OVERFLOW": "1",
            "PLATFORM_OPS_GATEWAY_PROCESS_COUNT": "1",
            "PLATFORM_OPS_DB_POOL_SIZE": "3",
            "PLATFORM_OPS_DB_MAX_OVERFLOW": "2",
            "PLATFORM_OPS_WORKER_PROCESS_COUNT": "1",
            "PLATFORM_OPS_WORKER_DB_POOL_SIZE": "2",
            "PLATFORM_OPS_WORKER_DB_MAX_OVERFLOW": "1",
            "ROSTER_AUTOMATION_PROCESS_COUNT": "1",
            "ROSTER_AUTOMATION_DB_POOL_SIZE": "1",
            "ROSTER_AUTOMATION_DB_MAX_OVERFLOW": "1",
        }
        with patch.dict(os.environ, values, clear=False):
            budget = validate_connection_budget()
        self.assertTrue(budget.valid)
        self.assertEqual(budget.roles["api"], 15)
        self.assertEqual(budget.roles["worker"], 15)
        self.assertEqual(budget.roles["scheduled_worker"], 3)
        self.assertEqual(budget.roles["evidence_worker"], 2)
        self.assertEqual(budget.roles["platform_ops_gateway"], 5)
        self.assertEqual(budget.roles["platform_ops_worker"], 3)
        self.assertEqual(budget.roles["rostering_automation"], 2)
        self.assertEqual(budget.projected, 45)
        self.assertEqual(budget.usable, 85)


if __name__ == "__main__":
    unittest.main()
