"""Low-overhead per-request SQL query counting for performance gates."""
from __future__ import annotations

from contextvars import ContextVar, Token
from typing import MutableMapping

from sqlalchemy import event

from .database import read_engine, write_engine

_counter: ContextVar[MutableMapping[str, int] | None] = ContextVar("db_query_counter", default=None)


def begin_counting() -> Token:
    # The mutable mapping is intentionally shared with Starlette's copied
    # thread context, so sync endpoints contribute to the parent request total.
    return _counter.set({"count": 0})


def query_count() -> int:
    return int((_counter.get() or {}).get("count", 0))


def end_counting(token: Token) -> None:
    _counter.reset(token)


def _before_cursor_execute(*_args, **_kwargs) -> None:
    counter = _counter.get()
    if counter is not None:
        counter["count"] = counter.get("count", 0) + 1


for candidate in {write_engine, read_engine}:
    event.listen(candidate, "before_cursor_execute", _before_cursor_execute)
