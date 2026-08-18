from __future__ import annotations

from fastapi import HTTPException

_INSTALLED = False


def install(router_module) -> None:
    """Preserve machine-readable roster workflow errors at the HTTP boundary.

    The legacy router translates generic ValueError/RuntimeError instances into
    a stable API envelope.  New workflow services additionally expose ``code``,
    ``message`` and ``details`` attributes.  This compatibility seam keeps that
    domain information intact without duplicating endpoint implementations.
    """

    global _INSTALLED
    if _INSTALLED:
        return

    original_translate = router_module._translate

    def translate(exc: Exception, *, default_code: str) -> HTTPException:
        code = getattr(exc, "code", None)
        details = getattr(exc, "details", None)
        message = getattr(exc, "message", None)
        if isinstance(code, str) and code:
            status_code = 403 if code.endswith("FORBIDDEN") or code.endswith("ACCESS_DENIED") else 409
            return HTTPException(
                status_code=status_code,
                detail={
                    "detail": str(message or exc),
                    "error_code": code,
                    "field_errors": {},
                    "conflicts": [],
                    "retryable": code.endswith("STALE") or "REVISION_CONFLICT" in code,
                    "metadata": details if isinstance(details, dict) else {},
                },
            )
        return original_translate(exc, default_code=default_code)

    router_module._translate = translate
    _INSTALLED = True


__all__ = ["install"]
