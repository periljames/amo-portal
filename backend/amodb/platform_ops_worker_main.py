from __future__ import annotations

import asyncio
import signal

from amodb.apps.platform.ops_worker import durable_command_worker
from amodb.database import dispose_engines


async def _run() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # pragma: no cover - Windows/dev fallback
            pass
    try:
        await durable_command_worker(stop)
    finally:
        dispose_engines()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
