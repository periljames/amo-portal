#!/usr/bin/env python3
"""Re-run failed GitHub Actions jobs for the exact current head of one PR.

The script never marks checks successful and never re-runs successful or in-progress
workflows. It asks GitHub to re-run only failed jobs from completed pull-request
workflow runs associated with both the requested PR number and its current head SHA.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


FAILED_CONCLUSIONS = {
    "action_required",
    "cancelled",
    "failure",
    "stale",
    "startup_failure",
    "timed_out",
}
TRANSIENT_HTTP = {429, 500, 502, 503, 504}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Re-run failed GitHub Actions jobs for an exact PR head."
    )
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY", ""))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.repo or "/" not in args.repo:
        parser.error("--repo owner/name or GITHUB_REPOSITORY is required")
    return args


class GitHubAPI:
    def __init__(self, repo: str, token: str) -> None:
        self.repo = repo
        self.token = token
        self.base = f"https://api.github.com/repos/{repo}"

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        attempts = 4 if method == "GET" else 1
        delay = 2.0
        for attempt in range(1, attempts + 1):
            request = urllib.request.Request(
                f"{self.base}{path}",
                data=body,
                method=method,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {self.token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "amo-portal-ci-recheck",
                    **({"Content-Type": "application/json"} if body is not None else {}),
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    raw = response.read()
                    return json.loads(raw) if raw else None
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                if method == "GET" and exc.code in TRANSIENT_HTTP and attempt < attempts:
                    retry_after = exc.headers.get("Retry-After")
                    sleep_for = float(retry_after) if retry_after and retry_after.isdigit() else delay
                    print(
                        f"Transient GitHub HTTP {exc.code} for {path}; retrying in {sleep_for:.1f}s.",
                        file=sys.stderr,
                    )
                    time.sleep(sleep_for)
                    delay = min(delay * 2, 30.0)
                    continue
                raise RuntimeError(
                    f"GitHub API {method} {path} failed with HTTP {exc.code}: {detail[:2000]}"
                ) from exc
            except urllib.error.URLError as exc:
                if method == "GET" and attempt < attempts:
                    print(
                        f"Transient GitHub connection error for {path}: {exc.reason}; retrying in {delay:.1f}s.",
                        file=sys.stderr,
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, 30.0)
                    continue
                raise RuntimeError(f"GitHub API {method} {path} failed: {exc.reason}") from exc
        raise RuntimeError(f"GitHub API {method} {path} exhausted retries")


def current_pr_head(api: GitHubAPI, pr_number: int) -> str:
    payload = api.request("GET", f"/pulls/{pr_number}")
    if not isinstance(payload, dict):
        raise RuntimeError("GitHub returned an invalid pull-request response")
    if payload.get("state") != "open":
        raise RuntimeError(f"PR #{pr_number} is not open")
    head = ((payload.get("head") or {}).get("sha") or "").strip()
    if not head:
        raise RuntimeError("PR head SHA is missing")
    return head


def _belongs_to_pr(row: dict[str, Any], pr_number: int) -> bool:
    pull_requests = row.get("pull_requests") or []
    return any(
        isinstance(item, dict) and int(item.get("number") or 0) == pr_number
        for item in pull_requests
    )


def pull_request_runs(
    api: GitHubAPI,
    *,
    head_sha: str,
    pr_number: int,
) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(
        {
            "event": "pull_request",
            "head_sha": head_sha,
            "per_page": 100,
        }
    )
    payload = api.request("GET", f"/actions/runs?{query}")
    rows = (payload or {}).get("workflow_runs") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("GitHub returned an invalid workflow-runs response")
    return [
        row
        for row in rows
        if str(row.get("head_sha") or "") == head_sha and _belongs_to_pr(row, pr_number)
    ]


def main() -> int:
    args = parse_args()
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        print("GITHUB_TOKEN is required", file=sys.stderr)
        return 2

    api = GitHubAPI(args.repo, token)
    initial_head = current_pr_head(api, args.pr)
    rows = pull_request_runs(api, head_sha=initial_head, pr_number=args.pr)
    failed = [
        row
        for row in rows
        if row.get("status") == "completed"
        and str(row.get("conclusion") or "").lower() in FAILED_CONCLUSIONS
    ]

    print(f"PR #{args.pr} exact head: {initial_head}")
    print(f"Matched pull-request workflow runs: {len(rows)}")
    if not failed:
        print("No completed failed GitHub Actions runs require re-checking.")
        return 0

    rerun_count = 0
    for row in sorted(failed, key=lambda item: int(item.get("id") or 0)):
        current_head = current_pr_head(api, args.pr)
        if current_head != initial_head:
            print(
                f"PR head moved from {initial_head} to {current_head}; refusing to re-run stale checks.",
                file=sys.stderr,
            )
            return 3

        run_id = int(row["id"])
        name = str(row.get("name") or row.get("display_title") or run_id)
        conclusion = str(row.get("conclusion") or "unknown")
        html_url = str(row.get("html_url") or "")
        print(f"{name}: {conclusion} — {html_url}")
        if args.dry_run:
            continue
        api.request("POST", f"/actions/runs/{run_id}/rerun-failed-jobs")
        rerun_count += 1
        print(f"Requested failed-job re-run for workflow run {run_id}.")

    if args.dry_run:
        print(f"Dry run: {len(failed)} failed workflow run(s) would be re-checked.")
    else:
        print(f"Requested re-check for {rerun_count} failed workflow run(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
