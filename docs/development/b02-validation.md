# B02 validation record

Validation date: 2026-10-02. Scope: infrastructure/bootstrap only; B03+ is absent.

## Executed checks

| Check | Result |
| --- | --- |
| `docker compose config --quiet` and parsed configuration | Passed: seven services; only loopback Nginx publication; no database environment in FastAPI |
| `python3 scripts/setup-env.py`, repeat invocation and empty environment | Passed: ignored 0600 credentials; no overwrite; Compose rejects missing credentials |
| Frontend `npm ci --no-audit --no-fund` and `npm run build` | Production compile/type/template build passed; initial bundle approximately 121 kB |
| Local Laravel `composer test`, platform requirements and route listing | Four tests/13 assertions passed on PHP 8.4; only `GET /api/health` is registered |
| Local FastAPI `python -m pytest -q -p no:cacheprovider` | Two tests passed |
| Compose application image builds with the documented local CA/source override | All current application images built; targeted Laravel/frontend rebuilds verified the final Dockerfiles |
| `docker compose pull postgres redis nginx` | Passed after Docker Hub login |
| `docker compose up -d --wait --wait-timeout 180` | All seven services reached healthy/running state |
| `python3 scripts/verify-stack.py` | Passed: live health, actual bindings, CPU/memory caps, non-root application users, credential boundaries, Angular assets, Laravel readiness, internal FastAPI from worker, SQL, Redis, unused pgvector capability and worker liveness |
| Live Chromium browser against `http://127.0.0.1:8080` | Angular boots, calls real Laravel through Nginx, displays ready state; no page errors or analysis form |
| Nginx boundary checks in the live verification script | Unexpected Host, external Origin and null Origin rejected with 403; internal run and analysis submission routes absent (404) |
| FastAPI test-image build and `docker run --rm ai-software-engineer-ai-test` | Two tests passed on selected Python 3.12 image as unprivileged user |
| `docker compose down` and named-volume inspection | Containers/network removed successfully; PostgreSQL data volume preserved |
| Laravel test-image build and `docker run --rm ai-software-engineer-backend-test` | Four tests/13 assertions passed on selected PHP 8.3.35 image as unprivileged user |
| Final Compose restart, live verification and Chromium browser | Passed again after shutdown; all seven services healthy with the preserved PostgreSQL volume |
| PHP/Python syntax checks, `git diff --check`, ignore/lockfile checks | Passed; no tracked secrets or dependency/build/cache artifacts |

All B02 acceptance criteria were demonstrated. The final stack is running with
seven healthy services; no integration blocker remains.

## Environment recovery and bootstrap fixes

The managed Docker daemon initially returned Docker Hub HTTP 429 for anonymous
pulls. Login resolved that blocker. HTTPS builds require the managed proxy CA;
it is supplied through an optional BuildKit secret, with TLS verification enabled
and no CA copied into image layers. The network permits Git dependency access but
blocks GitHub archive API requests; the local override selects Composer's supported
`COMPOSER_INSTALL_MODE=source`. Normal builds default to distribution archives.

Container validation caught restrictive checkout/asset permissions. Dockerfiles
now normalize application/static-asset readability and assign AI test sources to
the test user. Loopback wget probes explicitly disable inherited proxies. Laravel
bootstrap uses in-memory sessions/cache and creates no framework or domain tables.

The environment's VFS driver copies whole filesystem layers. Source dependency Git
histories exhausted its 32 GiB disk during test builds. Laravel images now discard
Composer download caches and dependency Git metadata after installation. Recovery
removed only individually identified B02 caches/obsolete images and dependency
histories/mirrors created by this task; credentials, unmatched caches, application
sources and PostgreSQL data were preserved. No broad Docker prune or volume deletion
was performed.

Remaining non-failing dependency warnings: source-mode Composer autoload reports
upstream Flysystem class ambiguity; FastAPI's test dependencies report an AnyIO
alias deprecation. These do not prevent package discovery, runtime health or tests.

## Scope review

No analysis routes, domain migrations/models, jobs, reliable handoff, acquisition,
LLM adapters, findings, embeddings or vector use were added. No accepted ADR or
normative B01 contract changed. PostgreSQL exposes pgvector extension files but
`pg_extension` contains no activated vector extension; there is no application-level
vector use. B03+ and production deployment remain out of scope.
