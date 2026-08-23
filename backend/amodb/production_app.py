"""Production ASGI application with cross-replica admission and runtime guards."""
from __future__ import annotations

from . import main as core
from .distributed_rate_limit import DistributedAuthRateLimitMiddleware, RedisAuthRateLimiter
from .runtime_concurrency import install_runtime_concurrency

runtime_maintenance = install_runtime_concurrency(core)
auth_rate_limiter = RedisAuthRateLimiter()
app = core.app
app.add_middleware(DistributedAuthRateLimitMiddleware, limiter=auth_rate_limiter)


async def _verify_production_dependencies() -> None:
    await auth_rate_limiter.verify_startup()


async def _close_production_dependencies() -> None:
    await auth_rate_limiter.close()


app.add_event_handler("startup", _verify_production_dependencies)
app.add_event_handler("shutdown", _close_production_dependencies)
