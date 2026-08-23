"""Platform package runtime wiring."""
from __future__ import annotations

from amodb.apps.platform.command_queue_install import (
    install_platform_command_queue_overrides as _install_platform_command_queue_overrides,
)
from amodb.apps.platform.managed_ai_provider_policy import (
    install_managed_ai_provider_policy as _install_managed_ai_provider_policy,
)
from amodb.apps.platform.ai_execution_policy import (
    install_ai_execution_policy as _install_ai_execution_policy,
)

_install_platform_command_queue_overrides()
_install_managed_ai_provider_policy()
_install_ai_execution_policy()

# Keep the post-cleanup package wiring narrow: the base Platform router remains
# authoritative and this PR contributes only the governed AI control surface.
from amodb.apps.platform.router import router as _platform_router  # noqa: E402
from amodb.apps.platform.ai_router import router as _ai_router  # noqa: E402

_platform_router.include_router(_ai_router)

__all__ = ["_install_platform_command_queue_overrides"]
