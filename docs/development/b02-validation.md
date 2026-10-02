# B02 validation record

Validation date: 2026-10-02. Scope: infrastructure/bootstrap only; B03+ is absent.

## Executed checks

| Check | Result |
| --- | --- |
| `docker compose config --quiet` | Passed |
| Parsed `docker compose config --format json` | Exactly seven expected services; only Nginx published, at `127.0.0.1:8080`; no database environment in FastAPI |
| `python3 scripts/setup-env.py` and repeat invocation | Generated ignored `.env` at 0600; second invocation refused overwrite and preserved contents |
| `docker compose --env-file /dev/null config --quiet` with credential variables absent | Correctly rejected missing credentials |
| Frontend `npm ci --no-audit --no-fund` and `npm run build` | Production compile/type/template build passed; initial bundle approximately 121 kB |
| FastAPI `python -m pytest -q -p no:cacheprovider` from `services/ai` | Two tests passed; one dependency deprecation warning |
| Chromium browser check of built Angular assets | Passed: bootstrap, ready/unavailable same-origin health fixtures, no analysis form, no page errors; used temporary Playwright tooling, not the Compose backend |
| PHP syntax checks on bootstrap sources | Passed using a temporary PHP 8.4 runtime |
| Composer dependency resolution / lockfile | Laravel 12 with dependency resolution constrained to PHP 8.3; standard source mode used because environment blocks GitHub archive API |
| Local Nginx syntax and HTTP boundary checks | Passed using temporary Nginx 1.26.3, with upstream names/listener/temp paths adapted for local testing; edge health 200, unexpected Host/Origin and null Origin 403, internal route 404 |
| Python compilation, `git diff --check`, ignore checks | Passed |

Laravel `composer test` passed with **4 tests and 13 assertions** using temporary
PHP 8.4.24: dependency readiness, redacted PostgreSQL/Redis failure responses and
absent analysis routes. `artisan route:list --except-vendor` exposes only
`GET /api/health`. Source-mode Composer autoload emitted upstream Flysystem class
ambiguity warnings; package discovery succeeded. Tests exposed Laravel's default
database session driver, corrected with an in-memory bootstrap session driver
without session tables. The selected PHP 8.3 container remains unverified.

## Docker integration blocker

The managed Docker 28.4 daemon and Compose 2.40.3 are available. Base-image
`docker pull` attempts, `docker compose build`, and `docker compose up -d --wait
--wait-timeout 180` were attempted. Docker Hub rejected anonymous pulls with
HTTP 429 / `toomanyrequests`. `docker compose ps` showed no running containers.

Consequently these checks are **not verified** in this environment:

- Build completion for the service and test images.
- Starting all seven services and container health convergence.
- Angular and Laravel HTTP behavior through the actual containerized Nginx.
- Actual host bindings on running containers.
- Internal FastAPI access from the Compose worker.
- PostgreSQL/pgvector availability and SQL connectivity in the selected image.
- Redis connectivity and continuous Laravel worker liveness in Compose.
- Container-based framework tests on the selected PHP 8.3/Python 3.12 images.

The [documented startup and verification commands](local-stack.md) and
`scripts/verify-stack.py` provide these checks once pulls are available. Authenticate
Docker Hub in the same environment, then rerun them. Local framework/configuration
checks do not establish successful Compose integration. B02's service-start
acceptance remains pending integration verification; every criterion cannot yet be
claimed as demonstrated.

## Scope review

No analysis routes, domain migrations/models, jobs, reliable handoff, acquisition,
LLM adapters, findings, embeddings or vector use were added. No accepted ADR or
normative B01 contract changed. Credentials and generated dependency/build/cache
artifacts are ignored; only dependency manifests/lockfiles and bootstrap sources
are intended for Git. PostgreSQL durable data is a named volume; Redis is transient.
