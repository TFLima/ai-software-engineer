# B12 operations and local data lifecycle

B12 adds operational events, an operator inspection command, terminal-result
retention and periodic orphan workspace cleanup. Laravel remains the only
persistent data owner. No public API/schema, provider or analysis stage changes.

## Local retention policy

`ANALYSIS_RETENTION_DAYS` defaults to 30, with supported integer values 1–3650.
Invalid configuration fails Laravel startup. Compose forwards it to API, worker
and scheduler. The scheduler runs `analyses:purge` hourly. Eligibility is measured
from the terminal `finished_at`, not submission time. Queued/running rows are
never eligible; the final row lock rechecks status and cutoff, serializing with
operator retry and result persistence. Foreign keys remove attempts and findings
atomically with the parent. Retained completed results remain immutable.

Deletion removes submission idempotency records too: replaying a deleted key
creates a new analysis. Existing UI links return `analysis_not_found`. It does
not erase backups, Docker log history, or data already sent to a provider.
Retention is a conservative local default, not a measured optimum: tune it after
observing result counts/storage and the operator's useful review window. No
production retention commitment or automatic budget increase is implied.

```sh
# Expired terminal records only; also run hourly by scheduler.
docker compose exec -T scheduler php artisan analyses:purge
# Immediate, explicit deletion of one completed/failed analysis.
docker compose exec -T scheduler php artisan analyses:purge --id=<analysis-id>
# Safe metadata only: queue age, attempt IDs/status, errors, timings and token usage.
docker compose exec -T scheduler php artisan analyses:inspect <analysis-id>
```

No-match explicit deletion exits unsuccessfully; automatic no-op purge succeeds.
No cancellation/deletion HTTP route is introduced.

## Visibility and workspace lifecycle

FastAPI emits JSON `analysis_finished` events with analysis/attempt IDs, safe
outcome/error/stage, per-stage milliseconds and token counters. Unknown usage
stays null. Events exclude repository URL, source paths/text, findings, prompts,
provider output, credentials and exception bodies. Existing queue-publication
warnings remain available in Laravel. `analyses:inspect` reads persisted validated
metadata without printing findings/evidence or full provenance. Queue age uses
submission time for initial waiting and scheduled retry time for queued retries;
future retry times report zero. Closed-attempt timings/usage remain visible until
retention removes the parent; transport-lost metadata can remain unavailable.

```sh
docker compose logs --tail=100 ai worker scheduler
```

Snapshots now live under private `/tmp/ase-workspaces` in the AI container.
Normal success/failure cleanup remains immediate. Failures emit
`snapshot_cleanup_failed` with request correlation IDs. A lifespan task runs an
initial sweep and then every five minutes, under the same single execution slot
as analysis. It cannot delete an executing snapshot. Direct `ase-snapshot-` child
directories matching the generated eight-character suffix become eligible after
one hour, well above the 240-second invocation and cleanup allowance. Fresh and
unrelated entries and symlink roots are preserved; nested symlink targets are
not followed. Each pass bounds deletion attempts to 100 and stops scanning after
10 seconds (an in-progress filesystem removal must finish). Failures are counted
and retried next pass without logging filesystem paths or exception content.
A sweep may briefly return the normal retryable overload response to a new run.
Container recreation removes its ephemeral workspace layer.

## Startup and recovery

Use `python3 scripts/setup-env.py` for initial ignored runtime settings, then
`docker compose up -d --build` and the checks in [local setup](local-stack.md).
Keep paid generation disabled until the B08 disclosure/configuration is satisfied.
After retention changes, recreate services with the same Compose command.

For a queued analysis, inspect queue age and worker/scheduler health; restore
Redis/worker availability and run `analyses:reconcile` on the scheduler. For a
crashed running attempt, wait for its 285-second lease before reconciliation;
never resend its internal run POST. Reconciliation fences late results and may
schedule the one automatic retry. After correcting a transient terminal failure,
run `docker compose exec -T worker php artisan analyses:retry <analysis-id>`;
only eligible transient failures within the three-attempt lifetime cap reopen.
Completed and policy/schema failures require a new submission, not operator retry.
See [B04](b04-validation.md) and [B10](b10-validation.md) for existing recovery rules.

## Verification and remaining limits

- `cd services/ai && python -m pytest -q -p no:cacheprovider`: 323 passed;
  one existing AnyIO deprecation warning.
- `python -m compileall -q services/ai/app services/ai/tests`: passed.
- `git diff --check`: passed.

New fixtures cover old/fresh/unrelated workspace handling, symlink isolation,
bounded deletion batches, correlated cleanup failures, safe event fields and
cleanup exclusion while an analysis holds the execution slot.
Existing 317 tests cover real pipeline components with fake provider/transport,
cleanup on success/failure/cancellation and all earlier contract regressions.
Laravel `OperationsTest` adds terminal cascading deletion, preservation of
pending work, explicit deletion, idempotency expiry, inspection and invalid IDs.
PHP, Composer and Docker are unavailable here: that PostgreSQL-backed suite,
retention/retry race execution and scheduled Compose behavior remain unverified.
Run the backend test procedure in [local setup](local-stack.md) before release.
B13 integrated acceptance and live finding usefulness/cost assessment remain
separate; no paid provider call or live repository analysis was performed.
