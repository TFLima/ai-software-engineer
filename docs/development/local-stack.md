# Local service stack (B02–B04)

B02 supplies infrastructure and operational health. B03 adds analysis, attempt and
finding tables plus the Laravel submission/status/findings API. B04 adds Redis jobs,
bounded attempts, an authenticated internal boundary and a reconciliation scheduler.
B05–B08 acquisition, selection, context and LLM generation are independently callable; endpoint integration, embeddings, RAG and the submission UI remain planned. See [B08 configuration and validation](b08-validation.md): provider calls are disabled by default, and Compose does not yet inject provider credentials.
The normative [B01 contracts](../contracts/README.md) remain unchanged.

## Prerequisites and environment

- Docker Engine/Desktop with Compose v2.20+ and BuildKit.
- Python 3.10+ for the local credential generator and verification script.
- Internet access to Docker Hub and npm, Composer/Packagist, PyPI and Debian
  package repositories for initial image/dependency downloads.
- At least 4 GiB of memory available to Docker and free host port 8080.

Run from the repository root:

```sh
python3 scripts/setup-env.py
docker compose config --quiet
docker compose up --build -d --wait --wait-timeout 180
docker compose exec -T api php artisan migrate --force
python3 scripts/verify-stack.py
```

The generator creates an ignored `.env` with mode 0600 and independent random
`APP_KEY` (Laravel AES-256 key), `DB_PASSWORD` (PostgreSQL password), and
`AI_INTERNAL_SECRET` (worker/FastAPI bearer secret). It refuses
to overwrite an existing file and never prints credentials. `.env.example` lists
the required stack secrets with empty values and standalone B08 provider settings; Compose rejects missing/empty stack secrets.
Do not paste real credentials into tracked files. Avoid publishing `docker compose
config` or container inspection output containing environment values.

Database name/user are `ai_software_engineer`; Laravel host/port settings are
provided explicitly in Compose. Laravel uses the Predis PHP client for Redis. All three
Laravel processes share the application image/code and environment. Only `api`
defines the backend build; `worker` consumes `ai-software-engineer-backend:local`
with `pull_policy: never`, avoiding concurrent exports of the same tag. Run the
full-stack build/start command above before starting the worker on its own.
FastAPI receives no database credentials. Only worker and FastAPI receive the
internal bearer secret; API, scheduler and frontend do not need it. If upgrading
an existing B02/B03 `.env`, preserve its existing values and run:

```sh
python3 scripts/setup-env.py --add-internal-secret
```

The flag adds only the missing random secret without displaying it. Rebuild and
restart the stack after adding it.

## URLs, topology and health

Open <http://localhost:8080> or <http://127.0.0.1:8080>. The Angular page reports
application readiness using same-origin `GET /api/health`; it offers no analysis
workflow. B03 API clients can submit a public GitHub URL to `POST /api/analyses`
with JSON and an `Idempotency-Key`, then read `GET /api/analyses/{id}`. Submitted
analyses are delivered to the internal service. Until B10 supplies the pipeline,
the boundary returns terminal `configuration_error` without source/provider work. Host port 8080 and its two exact loopback origins are intentional local
settings. Changing the port requires changing the edge Host/Origin allowlists,
`APP_URL`, verification script and documentation together.

| Compose service | Internal port | Health check | Role |
| --- | --- | --- | --- |
| `nginx` | 8080 | `GET /healthz` | Only host mapping: `127.0.0.1:8080:8080` |
| `frontend` | 8080 | `GET /healthz` | Built Angular/TypeScript assets served by an internal Nginx process |
| `api` | 8000 | `GET /api/health` | Laravel 12/PHP 8.3; readiness queries PostgreSQL and pings Redis |
| `worker` | None | `php worker-health.php` | Laravel `queue:work redis`; PID 1 process identity and Redis connectivity |
| `scheduler` | None | `php scheduler-health.php` | Laravel `schedule:work`; runs reconciliation every 30 seconds |
| `ai` | 8000 | `GET /health` | Python 3.12/FastAPI; internal process health only |
| `postgres` | 5432 | `pg_isready` | PostgreSQL 17 with pgvector available; named durable volume |
| `redis` | 6379 | `redis-cli ping` | Transient queue; no disk persistence, noeviction memory policy |

All services share a Compose bridge network. Only Nginx publishes a host port;
image `EXPOSE` metadata does not publish a port. Edge `/api/` goes to Laravel,
`/` goes to frontend, and `/internal` plus `/internal/` are rejected. FastAPI has
no public routing. Edge accepts only `localhost:8080`/`127.0.0.1:8080` Host and
matching loopback Origin values (or omitted Origin for local clients). It rejects
unexpected Host/Origin, including `Origin: null`, with 403 and adds no CORS access.
A 4 KiB edge body cap preserves the B01 public submission ceiling. Local processes
are trusted under the single-operator policy.

CPU/memory caps are explicit for every service. Laravel and FastAPI run as
unprivileged users. pgvector's extension files are available from the selected
image; B02 does not activate the extension or create vector/application tables.

Health dependencies gate initial startup only. Compose does not provide reliable
handoff on its own. B04 application code implements durable claims, retries and
reconciliation. Worker timeout 270s, Redis reservation 300s and framework
`--tries=1` preserve the B01 ordering. Worker health is process/queue readiness, not proof
that a domain job can run. FastAPI and edge health checks do not assert application
or AI pipeline completeness.

## Verification and troubleshooting

```sh
docker compose ps
curl --fail http://127.0.0.1:8080/healthz
curl --fail http://127.0.0.1:8080/api/health
curl --fail http://127.0.0.1:8080/
python3 scripts/verify-stack.py
docker compose exec -T worker php -r "echo file_get_contents('http://ai:8000/health');"
docker compose exec -T postgres psql -U ai_software_engineer -d ai_software_engineer -c 'SELECT 1;'
docker compose exec -T redis redis-cli ping
docker compose logs --tail=50 api worker ai nginx
```

The verification script checks all eight healthy/running containers, actual host
port bindings, frontend JS delivery, Laravel readiness, internal FastAPI access,
SQL, Redis, worker liveness, pgvector availability without activation, rejected
Host/Origin and the absent internal route. It exits nonzero on any failure.
Logs and failed health responses must not disclose connection secrets.

Laravel uses its development HTTP server; this is a local bootstrap, not production
serving/scaling infrastructure. Rebuild after code/dependency changes. There are
no bind-mounted application sources or hot reload in this minimal topology.
If PostgreSQL credentials change after its volume is initialized, the existing
role password must be changed deliberately; altering `.env` alone does not update
that volume. Preserve `.env` for subsequent starts.

A Docker Hub `toomanyrequests` response blocks image build/start; authenticate with
`docker login` in the environment running these commands and retry. Do not infer
runtime success from a valid Compose file.

## Framework checks

```sh
# Angular compile/type/template checks (also run during image build):
cd services/frontend
npm ci
npm run build
cd ../..

# Laravel tests use a disposable PostgreSQL database on a private test network:
docker network create b03-tests
docker run -d --rm --name b03-test-postgres --network b03-tests \
  -e POSTGRES_DB=ai_software_engineer_test -e POSTGRES_PASSWORD=local-test postgres:17
until docker exec b03-test-postgres pg_isready -U postgres -d ai_software_engineer_test; do sleep 1; done
docker build --target test -t ai-software-engineer-backend-test services/backend
docker run --rm --network b03-tests -e APP_ENV=testing \
  -e APP_KEY=base64:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= \
  -e DB_HOST=b03-test-postgres -e DB_DATABASE=ai_software_engineer_test \
  -e DB_USERNAME=postgres -e DB_PASSWORD=local-test \
  ai-software-engineer-backend-test
docker stop b03-test-postgres
docker network rm b03-tests

# FastAPI tests:
docker build --target test -t ai-software-engineer-ai-test services/ai
docker run --rm ai-software-engineer-ai-test
```

Laravel tests cover health, B03 submission/idempotency/read APIs and B04 claims,
retry caps, reconciliation, internal responses, stale fences and atomic persistence. Run them only against an isolated database named
`ai_software_engineer_test`; the suite refuses to reset another database.
FastAPI tests cover health, authentication, strict requests, ceilings, deadlines,
overload and the B10 pipeline with simulated GitHub and fake generation; docs remain disabled. With local
PHP 8.3+ and extensions available, use `composer install` and `composer test` in
`services/backend` with `DB_DATABASE=ai_software_engineer_test` and a separate
PostgreSQL test database. With Python 3.12, create a virtualenv, install
`services/ai/requirements-dev.txt`, then run `python -m pytest -q` from `services/ai`.
Lockfiles capture Angular and Laravel dependencies; Python's direct dependencies
are pinned in requirements files.

Builds optionally accept a BuildKit secret named `proxy_ca` for environments with
an HTTPS inspection proxy. Mount a combined public CA bundle for PHP/pip trust or
the proxy CA for Node; do not disable TLS verification or copy it into image layers.
For a managed environment, supply the bundle to each build:

```sh
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt --target base -t ai-software-engineer-backend:local services/backend
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt --target test -t ai-software-engineer-backend-test services/backend
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt --target base -t ai-software-engineer-ai:local services/ai
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt --target test -t ai-software-engineer-ai-test services/ai
```

For Compose builds in that environment, use a local ignored `compose.local.yaml`
override with `build.secrets: [proxy_ca]` on `frontend`, `api`, `ai`, and
a top-level `secrets.proxy_ca.file` pointing to the CA bundle; pass it with
`-f compose.yaml -f compose.local.yaml`. Normal local builds need no proxy secret.

If the environment permits Git access to `github.com` but blocks Composer archive
requests to `api.github.com`, explicitly select Composer's supported source mode
instead of relying on an automatic fallback (disabled in newer Composer versions).
Add these fields to the same local override:

```yaml
services:
  api:
    build:
      args:
        COMPOSER_INSTALL_MODE: source
```

Then build with `docker compose -f compose.yaml -f compose.local.yaml build` and
start with `docker compose up -d --wait --wait-timeout 180`. For a backend test-image
build in that environment, add `--build-arg COMPOSER_INSTALL_MODE=source` alongside
the `--secret` argument. Default builds use distribution archives. CA bundles and
overrides are local build inputs, not committed credentials or runtime mounts.
Laravel images discard Composer download caches and dependency Git metadata after
installation; these are build artifacts, not application runtime requirements.
Dockerfiles normalize source readability for unprivileged application processes,
including when the checkout was created with a restrictive local umask.

## Stop and data

```sh
docker compose stop    # preserve containers and PostgreSQL data
docker compose down   # remove containers/network, preserve named PostgreSQL volume
```

Redis contents are transient and lost when its container is recreated. Removing
PostgreSQL data is a separate destructive operation (`docker compose down --volumes`);
use it only for an intentional local reset. Migrations are explicit; no automatic
seeding runs. The scheduler can be invoked manually with `docker compose exec -T scheduler php
artisan analyses:reconcile`. Controlled transient retries use `docker compose exec
-T worker php artisan analyses:retry <analysis-id>`; this cannot reopen completed or
policy/schema failures. See [B04 behavior and validation](b04-validation.md).

Laravel bootstrap sessions/cache use
in-memory stores; B02 creates no session/cache/queue tables.

## Browser analysis flow (B11)

Open `http://127.0.0.1:8080`, enter a public GitHub URL and acknowledge the
source-transmission disclosure. The UI follows queued/running/completed/failed,
shows SHA/coverage and displays completed findings in pages of five. With the
default disabled provider configuration, the analysis fails safely with an
actionable configuration message. See [B10 provider setup](b10-validation.md)
and [B11 behavior and verification](b11-validation.md).

After updating frontend code, rebuild/recreate the frontend through
`docker compose up -d --build`. Each analysis has a local hash link such as
`http://127.0.0.1:8080/#analysis/<id>`; reloading it resumes reads without
resubmitting. Frontend-only checks run from `services/frontend`:

```sh
npm ci --no-audit --no-fund
npm test
npx playwright install chromium --only-shell
npm run test:browser
```

Contract tests need Node 22.18+ (native TypeScript stripping). Browser tests
serve the production build on loopback and mock the public API; no repository or
provider calls are made. Playwright is a development-only dependency. The runtime
frontend image serves built assets; it does not run tests or contain credentials.
