from __future__ import annotations

from collections.abc import Callable
import re

from fastapi import APIRouter


RoutePredicate = Callable[[object], bool]


def _route_shape(path: str) -> str:
    return re.sub(r"\{[^{}]+\}", "{}", path)


def _ambiguous_signatures(route_items: list[object]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    duplicates: set[tuple[str, str]] = set()
    for route_item in route_items:
        shape = _route_shape(str(getattr(route_item, "path", "")))
        for method in getattr(route_item, "methods", None) or ():
            if method in {"HEAD", "OPTIONS"}:
                continue
            signature = shape, method
            if signature in seen:
                duplicates.add(signature)
            seen.add(signature)
    return sorted(duplicates)


def _specificity(route_item: object, registration_index: int) -> tuple[int, int, int, int]:
    path = str(getattr(route_item, "path", ""))
    segments = [segment for segment in path.split("/") if segment]
    parameter_count = sum(1 for segment in segments if "{" in segment)
    literal_count = len(segments) - parameter_count
    return parameter_count, -literal_count, -len(segments), registration_index


def assert_unique_routes(api_router: APIRouter, *, label: str) -> None:
    duplicates = _ambiguous_signatures(list(api_router.routes))
    if duplicates:
        raise RuntimeError(f"{label} contains ambiguous route handlers: {duplicates}")


def promote_route_family(
    api_router: APIRouter,
    *,
    predicate: RoutePredicate,
    label: str,
) -> None:
    """Place a route family before catch-alls and reject ambiguous handlers."""

    registered = [route_item for route_item in api_router.routes if predicate(route_item)]
    if not registered:
        raise RuntimeError(f"{label} routes were not registered")

    duplicates = _ambiguous_signatures(registered)
    if duplicates:
        raise RuntimeError(f"{label} contains ambiguous route handlers: {duplicates}")

    registration_order = {id(route_item): index for index, route_item in enumerate(registered)}
    registered.sort(key=lambda route_item: _specificity(route_item, registration_order[id(route_item)]))

    remaining = [route_item for route_item in api_router.routes if not predicate(route_item)]
    catchall_index = next(
        (
            index
            for index, route_item in enumerate(remaining)
            if str(getattr(route_item, "path", "")).endswith("/{module_path:path}")
        ),
        len(remaining),
    )
    api_router.routes[:] = [
        *remaining[:catchall_index],
        *registered,
        *remaining[catchall_index:],
    ]
