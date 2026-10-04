# B03 validation record

Scope: relational storage and Laravel application API. B04 queue publication,
attempt claims, reconciliation and internal FastAPI execution remain pending.

## Checks performed

| Check | Result |
| --- | --- |
| Laravel PHPUnit against disposable PostgreSQL 17 database `ai_software_engineer_test` | 8 tests, 101 assertions passed; migrations applied from an empty database |
| PHP 8.3 syntax checks for app, routes, migrations and tests | Passed |
| Nginx 1.28 `nginx -t` with B03 edge configuration | Passed |
| Live HTTP through temporary Nginx → Laravel → PostgreSQL/Redis stack | Passed: health, submission, status, not-ready findings, replay, JSON 413, Host rejection |
| `docker compose config --quiet` | Passed |
| OpenAPI YAML parse and route/schema reference check | Passed |
| `git diff --check` | Passed |

The Laravel tests exercise canonical URLs, idempotent replay and changed-body
conflicts, invalid/duplicate JSON, validation, new-submission admission limits,
queued/running/failed findings readiness, status fields, empty and paginated
completed results, and unknown analysis IDs. Tests use a separate disposable
PostgreSQL container. No operator database or volume was reset. Temporary test
containers and network were removed afterward.

The managed environment's proxy rejected Composer's GitHub archive endpoint and
the full Laravel Git clone. The test image was built from a temporary copy of the
backend context whose locked GitHub distribution URLs were mapped to equivalent
`codeload.github.com` commit archives. The tracked lockfile was unchanged. Final
source directories were mounted into the test image for PHPUnit and the HTTP
smoke test. A full Compose restart/browser pass was not run for B03.

## Scope and behavior

The `analyses` row is the durable queue-publication intent at submission. B03
does not publish a Redis job; B04 will consume/reconcile queued rows and enforce
attempt transitions. The status/findings API already exposes the v1 shape, and
findings return `analysis_not_completed` until a completed result exists. The
tests create completed rows directly as fixtures; they do not claim the pipeline
can produce such rows yet.
