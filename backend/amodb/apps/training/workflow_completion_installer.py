from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .workflow_completion import install_training_workflow_completion


LEGACY_ASSESSMENT_PATHS = {
    "/assessments/{assessment_id}/attempt/start",
    "/assessments/{assessment_id}/attempt/autosave",
    "/assessments/{assessment_id}/attempt/submit",
    "/assessments/{assessment_id}/review",
    "/assessments/{assessment_id}/appeal",
}


def install_training_workflow_completion_without_legacy_assessment_routes(router_module) -> None:
    """Install the completion layer while withholding its superseded attempt paths.

    Deferrals, external learning, calendar/RSVP, OJT and authorization completion
    routes stay exactly where they are. Assessment attempt endpoints are installed
    once by ``canonical_assessment_routes`` so no hidden policy defaults survive.
    """

    router = router_module.router
    original_add_api_route: Callable[..., Any] = router.add_api_route

    def filtered_add_api_route(path: str, endpoint, *args, **kwargs):
        if path in LEGACY_ASSESSMENT_PATHS:
            return None
        return original_add_api_route(path, endpoint, *args, **kwargs)

    router.add_api_route = filtered_add_api_route  # type: ignore[method-assign]
    try:
        install_training_workflow_completion(router_module)
    finally:
        router.add_api_route = original_add_api_route  # type: ignore[method-assign]


__all__ = [
    "LEGACY_ASSESSMENT_PATHS",
    "install_training_workflow_completion_without_legacy_assessment_routes",
]
