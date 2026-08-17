"""Fail-fast database connection budgeting for a replicated portal fleet."""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict


def _number(name: str, default: int, *, minimum: int = 0) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def _pool_capacity(size_name: str, overflow_name: str, default_size: int, default_overflow: int) -> int:
    return _number(size_name, default_size) + _number(overflow_name, default_overflow)


@dataclass(frozen=True)
class ConnectionBudget:
    database_max: int
    admin_reserve: int
    migration_reserve: int
    usable: int
    projected: int
    external_pooler: bool
    roles: dict[str, int]

    @property
    def valid(self) -> bool:
        return self.projected <= self.usable

    def payload(self) -> dict:
        return {**asdict(self), "valid": self.valid, "remaining": self.usable - self.projected}


def connection_budget() -> ConnectionBudget:
    maximum = _number("DB_MAX_CONNECTIONS", 300, minimum=20)
    admin = _number("DB_ADMIN_CONNECTION_RESERVE", 20)
    migration = _number("DB_MIGRATION_CONNECTION_RESERVE", 5)
    usable = maximum - admin - migration
    external = (os.getenv("DB_EXTERNAL_POOLER") or "").lower() in {"1", "true", "yes", "on"}

    if external:
        roles = {
            "api": _number("PGBOUNCER_API_POOL_SIZE", 90),
            "workforce": _number("PGBOUNCER_WORKFORCE_POOL_SIZE", 45),
            "general_worker": _number("PGBOUNCER_GENERAL_POOL_SIZE", 35),
            "scheduled_worker": _number("PGBOUNCER_SCHEDULED_POOL_SIZE", 10),
            "read": _number("PGBOUNCER_READ_POOL_SIZE", 30),
        }
    else:
        api_pool = _pool_capacity("DB_POOL_SIZE", "DB_MAX_OVERFLOW", 20, 10)
        worker_pool = _pool_capacity(
            "PORTAL_WORKER_DB_POOL_SIZE",
            "PORTAL_WORKER_DB_MAX_OVERFLOW",
            2,
            1,
        )
        scheduled_pool = _pool_capacity(
            "PORTAL_SCHEDULED_DB_POOL_SIZE",
            "PORTAL_SCHEDULED_DB_MAX_OVERFLOW",
            2,
            1,
        )
        evidence_pool = _pool_capacity(
            "DOCUMENT_EVIDENCE_PACK_DB_POOL_SIZE",
            "DOCUMENT_EVIDENCE_PACK_DB_MAX_OVERFLOW",
            1,
            1,
        )
        ops_gateway_pool = _pool_capacity(
            "PLATFORM_OPS_DB_POOL_SIZE",
            "PLATFORM_OPS_DB_MAX_OVERFLOW",
            3,
            2,
        )
        ops_worker_pool = _pool_capacity(
            "PLATFORM_OPS_WORKER_DB_POOL_SIZE",
            "PLATFORM_OPS_WORKER_DB_MAX_OVERFLOW",
            2,
            1,
        )

        roles = {
            "api": _number("PORTAL_API_PROCESS_COUNT", 1, minimum=1) * api_pool,
            "worker": _number("PORTAL_WORKER_PROCESS_COUNT", 0) * worker_pool,
            "scheduled_worker": _number("PORTAL_SCHEDULED_PROCESS_COUNT", 0) * scheduled_pool,
            "evidence_worker": _number("DOCUMENT_EVIDENCE_PACK_PROCESS_COUNT", 0) * evidence_pool,
            "platform_ops_gateway": _number("PLATFORM_OPS_GATEWAY_PROCESS_COUNT", 0) * ops_gateway_pool,
            "platform_ops_worker": _number("PLATFORM_OPS_WORKER_PROCESS_COUNT", 0) * ops_worker_pool,
        }

    return ConnectionBudget(maximum, admin, migration, usable, sum(roles.values()), external, roles)


def validate_connection_budget() -> ConnectionBudget:
    budget = connection_budget()
    if budget.usable <= 0 or not budget.valid:
        raise RuntimeError(
            "Database connection budget exceeded: "
            f"projected={budget.projected}, usable={budget.usable}, roles={budget.roles}. "
            "Reduce process/pool counts or increase PostgreSQL max_connections intentionally."
        )
    return budget
