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


if __name__ == "__main__":
    unittest.main()
