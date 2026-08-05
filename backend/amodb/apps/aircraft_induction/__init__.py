"""Universal aircraft type library and tail induction bounded context."""

from . import bootstrap as _bootstrap  # noqa: F401
from .router import router

__all__ = ["router"]
