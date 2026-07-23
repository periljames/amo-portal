#!/usr/bin/env python3
"""Retry dependency/download commands only for recognised transient failures.

This wrapper deliberately does not retry test, lint, build, migration, or application
commands. A non-transient non-zero exit is returned immediately so real failures are
never converted into green checks.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path


TRANSIENT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b429\b",
        r"too many requests",
        r"rate[ -]?limit(?:ed| exceeded)?",
        r"secondary rate limit",
        r"connection (?:reset|aborted|refused)",
        r"remote end closed connection",
        r"remote end hung up",
        r"temporary failure",
        r"temporarily unavailable",
        r"service unavailable",
        r"bad gateway",
        r"gateway timeout",
        r"\b50[234]\b",
        r"timed? out",
        r"timeout",
        r"econnreset",
        r"etimedout",
        r"eai_again",
        r"socket hang up",
        r"tls handshake timeout",
        r"unexpected eof",
        r"could not resolve host",
        r"name or service not known",
        r"network is unreachable",
        r"connection broken",
        r"chunkedencodingerror",
        r"read timed out",
        r"download failed",
        r"failed to download",
        r"unable to download",
        r"npm err! code e(?:connreset|timedout|ai_again)",
    )
)


def _is_transient(output: str) -> bool:
    return any(pattern.search(output) for pattern in TRANSIENT_PATTERNS)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retry a command only when its failure output is recognisably transient."
    )
    parser.add_argument(
        "--attempts",
        type=_positive_int,
        default=int(os.getenv("CI_TRANSIENT_RETRY_ATTEMPTS", "4")),
    )
    parser.add_argument(
        "--initial-delay",
        type=_non_negative_float,
        default=float(os.getenv("CI_TRANSIENT_RETRY_INITIAL_DELAY", "5")),
    )
    parser.add_argument(
        "--max-delay",
        type=_non_negative_float,
        default=float(os.getenv("CI_TRANSIENT_RETRY_MAX_DELAY", "60")),
    )
    parser.add_argument("--label", default="command")
    parser.add_argument("--cwd", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("a command is required after --")
    return args


def main() -> int:
    args = parse_args()
    command = [str(part) for part in args.command]
    delay = min(args.initial_delay, args.max_delay)
    rendered = shlex.join(command)

    for attempt in range(1, args.attempts + 1):
        print(
            f"::group::{args.label} (attempt {attempt}/{args.attempts})\n$ {rendered}",
            flush=True,
        )
        try:
            completed = subprocess.run(
                command,
                cwd=str(args.cwd) if args.cwd else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                check=False,
            )
        except FileNotFoundError as exc:
            print(f"{exc}\n::endgroup::", flush=True)
            return 127
        except KeyboardInterrupt:
            print("Interrupted\n::endgroup::", flush=True)
            return 130

        output = completed.stdout or ""
        if output:
            print(output, end="" if output.endswith("\n") else "\n", flush=True)
        print("::endgroup::", flush=True)

        if completed.returncode == 0:
            return 0

        if not _is_transient(output):
            print(
                f"::error::{args.label} failed with exit code {completed.returncode}; "
                "output did not match a transient network/rate-limit signature, so it will not be retried.",
                flush=True,
            )
            return completed.returncode

        if attempt == args.attempts:
            print(
                f"::error::{args.label} still failed after {args.attempts} bounded transient attempts.",
                flush=True,
            )
            return completed.returncode

        print(
            f"::warning::{args.label} hit a recognised transient failure; retrying in {delay:.1f}s.",
            flush=True,
        )
        time.sleep(delay)
        delay = min(args.max_delay, max(delay * 2, 1.0))

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
