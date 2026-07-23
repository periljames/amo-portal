# CI Transient Failure and Recheck Policy

## Purpose

Repository checks must distinguish real product failures from temporary package-registry, network, GitHub Actions, or artifact-service failures without turning flaky code into a green build.

## Dependency installation

The affected backend and frontend workflows invoke `.github/scripts/retry_transient.py` only for dependency download and installation commands.

The wrapper:

- uses bounded exponential backoff;
- retries only recognised rate-limit, timeout, DNS, connection-reset, gateway, and service-unavailable signatures;
- immediately returns a non-transient exit code;
- never retries migrations, tests, type checks, builds, lint, worker execution, or application assertions.

A retry therefore cannot convert a deterministic test failure into success.

## Diagnostic artifacts

Diagnostic uploads use `continue-on-error: true`. Logs remain useful when artifact storage is available, but an artifact quota or upload-service failure does not override the result of the command that produced the log.

## Exact-head manual recheck

`Recheck Failed PR Jobs` is a manually dispatched workflow. It runs `.github/scripts/rerun_failed_pr_checks.py` with the requested pull-request number.

The script:

1. resolves the open pull request and records its current head SHA;
2. lists only `pull_request` workflow runs associated with both that PR number and exact SHA;
3. selects completed runs with failure, cancellation, timeout, stale, startup-failure, or action-required conclusions;
4. checks the PR head again before every mutation;
5. asks GitHub to rerun only failed jobs;
6. refuses to rerun stale-head checks if the branch moved.

Successful and in-progress runs are never restarted. The script does not create statuses, waive checks, or report success on behalf of GitHub Actions.

## Merge evidence

A pull request is merge-ready only when the current head—not an earlier commit—has passed the required schema, backend, frontend, migration, worker, and deployment gates. External review-service quotas are recorded as external limitations and are not represented as successful code review.
