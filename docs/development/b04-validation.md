# B04 reliable queue handoff

B04 supplies durable attempt orchestration and the internal HTTP boundary. It
builds on B03 (`b22f206`) on `feat/mvp-0.1-b04`. Repository acquisition, context,
provider calls and the executable pipeline remain B05–B10 work. The real internal
endpoint currently returns an authenticated `configuration_error` failure rather
than inventing findings. Successful envelopes in tests come from deterministic
fixtures, not repository/model execution.

## Behavior and operation

- Submission commits its PostgreSQL row before publishing a Redis job. A failed
  publication still returns the durable analysis ID; reconciliation republishes
  queued rows due for at least 30 seconds. Idempotent replay never allocates work.
- A global PostgreSQL advisory lock serializes admission and claims. A row lock
  selects one winner, one active global attempt and a fresh UUID. Duplicate,
  premature and terminal deliveries are no-ops. All effective limits are frozen
  in the attempt. The latest known source SHA pins subsequent attempts.
- The worker makes one authenticated POST per attempt, with no HTTP resend or
  framework execution retry. Its bounded streamed response is validated before
  persistence, including closed JSON objects, versions, HTTP mapping,
  retryability, provenance, coverage and evidence. Findings and successful state
  commit together. No raw upstream bodies, source, prompts or secrets are logged.
- The final transaction fences analysis/attempt identity, active state and the
  persisted deadline. A mismatched, closed or late response changes nothing.
  Database persistence failures propagate for lease recovery rather than being
  mislabeled as transport failures.
- A first transient failure schedules a fresh attempt after five seconds. A
  second failure is terminal. An explicit eligible operator retry permits one
  third lifetime attempt without resetting counters. Policy/schema failures and
  completed results cannot be reopened.
- Timeout ordering is 240s AI deadline < 255s HTTP < 270s job < 285s lease < 300s
  Redis reservation. Reconciliation runs every 30s and takes over a crashed
  invocation only after its lease. Expired attempts are closed immutably and an
  eligible retry is published with the five-second delay.
- Laravel config validates positive finite integer limits and their relationships
  at boot; PostgreSQL sessions use UTC for all deadline comparisons. FastAPI
  independently validates request limits against local ceilings, versions,
  canonical repository identity and the deadline. Its single active slot returns
  a safe overload envelope. Missing secret configuration blocks service startup.

Use the updated [local stack instructions](local-stack.md). Existing environments
must add the new secret without replacing database/app credentials:

```sh
python3 scripts/setup-env.py --add-internal-secret
docker compose up --build -d --wait --wait-timeout 180
docker compose exec -T api php artisan migrate --force
python3 scripts/verify-stack.py
```

Recovery/operator commands:

```sh
docker compose exec -T scheduler php artisan analyses:reconcile
docker compose exec -T worker php artisan analyses:retry <analysis-id>
```

The scheduler shares the application image, runs as the existing unprivileged
user, has no public port and checks process identity plus DB/Redis connectivity.
Only worker and FastAPI receive `AI_INTERNAL_SECRET`. FastAPI has no DB secrets;
Nginx still rejects `/internal`. No new migration is required beyond B03.

## Validation

| Check | Result |
| --- | --- |
| Laravel `php vendor/bin/phpunit` against isolated PostgreSQL | 22 tests, 209 assertions passed |
| FastAPI `python -m pytest -q -p no:cacheprovider` | 33 tests passed; one dependency deprecation warning |
| PHP syntax checks | Passed for application/config/bootstrap/tests and health scripts |
| Live Redis → queue worker → authenticated FastAPI → PostgreSQL | Passed; reconciled a lost publication and persisted the deliberate `configuration_error` with one attempt |
| Four independent PHP processes competing for one claim | Passed; exactly one attempt created |
| Internal OpenAPI request/success/failure examples | Validated against the published schemas |
| Git whitespace/diff checks | Passed |

PHP tests cover queue publication failure, lost messages, delay/lease boundaries,
automatic/operator caps, terminal failures, duplicate/stale/late responses,
transport loss without resend, missing/bad auth, oversized/non-JSON/duplicate-key
responses, SHA pinning, evidence/schema/metadata rejection and a database trigger
failure proving that partial findings and terminal state roll back together.

The managed environment has no Docker executable. Validation used extracted PHP
8.3/PostgreSQL 16/Redis binaries and Python dependencies in a disposable local
runtime, a separate `ai_software_engineer_test` database and loopback-only services.
A test-only identity shim allowed PostgreSQL's isolated test process to start in
the managed root execution environment; none of this runtime setup is project code
or deployment configuration. Composer installed the unchanged locked dependencies.
Full Compose rebuild/start, container health and browser checks were not executed
here. Run the documented stack verification on the operator's Docker machine.
No real repository/provider calls, paid operations, production deployment, commit,
push or PR creation were performed.
