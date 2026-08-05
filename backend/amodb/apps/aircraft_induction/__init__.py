"""Universal aircraft type library and tail induction bounded context."""

from . import bootstrap as _bootstrap  # noqa: F401
from .router import router
from .read_router import router as read_router

router.include_router(read_router)

__all__ = ["router"]
