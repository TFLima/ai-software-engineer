# B02 local service bootstrap

B02 supplies infrastructure and operational health only. B03 application API,
analysis/attempt/findings tables and lifecycle do not exist yet. There are no jobs,
repository acquisition, provider calls, embeddings, RAG or analysis submission UI.
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
python3 scripts/verify-stack.py
```

The generator creates an ignored `.env` with mode 0600 and independent random
`APP_KEY` (Laravel AES-256 key) and `DB_PASSWORD` (PostgreSQL password). It refuses
to overwrite an existing file and never prints credentials. `.env.example` lists
the required variables with empty values; Compose rejects missing/empty values.
Do not paste real credentials into tracked files. Avoid publishing `docker compose
config` or container inspection output containing environment values.

Database name/user are `ai_software_engineer`; Laravel host/port settings are
provided explicitly in Compose. Laravel uses the Predis PHP client for Redis. Both
Laravel processes share the application image/code and environment. Only `api`
defines the backend build; `worker` consumes `ai-software-engineer-backend:local`
with `pull_policy: never`, avoiding concurrent exports of the same tag. Run the
full-stack build/start command above before starting the worker on its own.
FastAPI receives no database credentials. No internal bearer secret is needed yet
because the run endpoint is absent; authentication must be implemented with that endpoint in B04/B10 before any analysis execution.

## URLs, topology and health

Open <http://localhost:8080> or <http://127.0.0.1:8080>. The Angular page reports
application readiness using same-origin `GET /api/health`; it offers no analysis
workflow. Host port 8080 and its two exact loopback origins are intentional local
settings. Changing the port requires changing the edge Host/Origin allowlists,
`APP_URL`, verification script and documentation together.

| Compose service | Internal port | Health check | Role |
| --- | --- | --- | --- |
| `nginx` | 8080 | `GET /healthz` | Only host mapping: `127.0.0.1:8080:8080` |
| `frontend` | 8080 | `GET /healthz` | Built Angular/TypeScript assets served by an internal Nginx process |
| `api` | 8000 | `GET /api/health` | Laravel 12/PHP 8.3; readiness queries PostgreSQL and pings Redis |
| `worker` | None | `php worker-health.php` | Laravel `queue:work redis`; PID 1 process identity and Redis connectivity |
| `ai` | 8000 | `GET /health` | Python 3.12/FastAPI; internal process health only |
| `postgres` | 5432 | `pg_isready` | PostgreSQL 17 with pgvector available; named durable volume |
| `redis` | 6379 | `redis-cli ping` | Transient queue; no disk persistence, noeviction memory policy |

All services share a Compose bridge network. Only Nginx publishes a host port;
image `EXPOSE` metadata does not publish a port. Edge `/api/` goes to Laravel,
`/` goes to frontend, and `/internal` plus `/internal/` are rejected. FastAPI has
no public routing. Edge accepts only `localhost:8080`/`127.0.0.1:8080` Host and
matching loopback Origin values (or omitted Origin for local clients). It rejects
unexpected Host/Origin, including `Origin: null`, with 403 and adds no CORS access.
A 4 KiB edge body cap preserves the B01 public submission ceiling; no submission
endpoint exists yet. Local processes are trusted under the single-operator policy.

CPU/memory caps are explicit for every service. Laravel and FastAPI run as
unprivileged users. pgvector's extension files are available from the selected
image; B02 does not activate the extension or create vector/application tables.

Health dependencies gate initial startup only. Compose does not provide reliable
handoff, retries, reconciliation or lifecycle correctness. Worker timeout 270s,
Redis reservation 300s and framework `--tries=1` preserve B01 ordering without
implementing B04 semantics. Worker health is process/queue readiness, not proof
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

The verification script checks all seven healthy/running containers, actual host
port bindings, frontend JS delivery, Laravel readiness, internal FastAPI access,
SQL, Redis, worker liveness, pgvector availability without activation, rejected
Host/Origin and absent analysis/internal routes. It exits nonzero on any failure.
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

# Container-based Laravel and FastAPI tests:
docker build --target test -t ai-software-engineer-backend-test services/backend
docker run --rm ai-software-engineer-backend-test
docker build --target test -t ai-software-engineer-ai-test services/ai
docker run --rm ai-software-engineer-ai-test
```

Laravel tests cover ready/dependency-failure health without exposing error details.
FastAPI tests cover health and the absence of analysis/docs endpoints. With local
PHP 8.3+ and extensions available, use `composer install` and `composer test` in
`services/backend`. With Python 3.12, create a virtualenv, install
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
use it only for an intentional local reset. No automatic migrations or seeders run. Laravel bootstrap sessions/cache use
in-memory stores; B02 creates no session/cache/queue tables.
