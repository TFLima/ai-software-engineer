# B13 integrated MVP verification

B13 adds a reproducible acceptance profile and deterministic cross-boundary
fixtures. This is verification work, not a new runtime provider or feature.
Native PostgreSQL/Compose acceptance passed. B12's PostgreSQL/Compose operations
checks also passed; the backlog records both items as complete.

## Captured public baseline and evaluation

Source: [octocat/Hello-World at 7fd1a60b01f91b314f59955a4e4d4e80d8edf11d](https://github.com/octocat/Hello-World/tree/7fd1a60b01f91b314f59955a4e4d4e80d8edf11d).
The public codeload archive was retrieved on 2026-10-14 without repository code,
hooks or dependency execution. The 261-byte archive is stored under
`services/ai/tests/fixtures/b13`; its manifest pins the immutable commit, SHA-256,
source URL, file count and capture date. Importing the test fixture verifies its
checksum. The only regular file is `README`, 13 bytes, one line: a greeting.

Fake generation returns one human-authored, low-severity advisory observation:
consider documenting usage and testing. Manual assessment: the observation is
supported by the entire inspected README, the line reference is exact, and the
recommendation is proportionate but has little practical depth. It does not
establish that tests are absent elsewhere or that the repository is insecure.
A valid empty response is tested separately and does not certify quality.
This evaluates plumbing and evidence consistency, not a model's reasoning,
recall, false-positive rate or usefulness on a realistic codebase. Reported fake
usage is deterministic test data, not observed paid usage or a cost measurement.

Synthetic scenario variants explicitly do not represent real GitHub projects.
Their URLs select fixtures only in the test ASGI entry point. They exercise:

| Scenario | Expected enforcement |
| --- | --- |
| `hello-world`, `empty` | Nonempty inspected context; valid findings or valid empty result |
| `invalid-json`, `bad-evidence` | Whole candidate rejected; no findings in error envelope |
| `missing`, `private` | Repository unavailable before generation |
| `oversize` | Actual streamed archive bytes exceed the server ceiling; no generation |
| `unsafe-path` | Traversal entry rejected; workspace removed |
| `provider-down` | Bounded transient operation retries; safe error and known SHA |
| `injection` | Repository AGENTS.md remains text; no process execution or attacker fetch |
| `xss` | Text may pass schema validation, but must render without HTML execution |

Python tests execute the real acquisition, selection, context, generation-budget,
validation and cleanup components with injected replay transport and fake model.
They check IDs, SHA, evidence, safe logs, no provider calls after acquisition
failures and workspace cleanup. A Python-produced B13 envelope also passes the
independent PHP validator; extending its evidence beyond line 1 is rejected.
Existing regression tests cover SSRF, limits, duplicate JSON keys, queue loss,
stale attempts, retry caps, atomic persistence and frontend escaping/polling.

## Full-stack acceptance command

Prerequisites are the [local-stack](local-stack.md) Docker/Compose requirements,
Node 22.18+ and the frontend development dependencies/browser:

```sh
cd services/frontend
npm ci --no-audit --no-fund
npx playwright install chromium --only-shell
cd ../..
python3 scripts/verify-mvp.py
```

Reserve loopback port 8080 for this run. The runner refuses an occupied port,
generates fresh credentials without printing them, and uses a random disposable
Compose project plus the exact test database `ai_software_engineer_test`. It
never selects the development project's volumes or database. Its `finally`
cleanup removes only that disposable project's containers/network/volumes.
Images/cache remain reusable. Container builds install only this trusted
platform's dependencies, never packages from analyzed inputs.

`compose.acceptance.yaml` selects the backend/AI test images and the separate
`acceptance_app` entry point from the AI **tests** tree. Production images do not
copy that tree. There is no fake-generation environment flag in the product;
normal runtime configuration still fails closed unless a real provider is
explicitly enabled. The acceptance overlay blanks the provider key and disables
real generation. Internal bearer authentication and all public/internal contracts
remain active. Acquisition replays the checksum-verified captured archive rather
than using external GitHub/network availability as a test dependency.

The runner builds the application, starts only PostgreSQL/Redis, runs the entire
Laravel suite before any worker/scheduler can mutate its test database, migrates,
then starts all eight services. It reuses the stack verifier for health, private
ports, loopback/Host/Origin restrictions and pgvector availability without use.
Real Playwright submissions follow Angular → Nginx → Laravel registration →
Redis worker → FastAPI acquisition/selection/context/fake generation/validation →
Laravel validation/transactional persistence → Angular SHA/evidence/coverage.
Successful results survive reload; malformed output fails with no displayed
findings; XSS is rendered as text. API calls in these browser tests are not mocked.
Queue loss, expiry, stale-result fencing and data deletion are regression gates
in the native PostgreSQL Laravel suite, not inferred from this happy path.

## Runtime issue found and corrected

The B12 initial workspace sweep previously ran in a background task after
readiness and could hold the sole execution slot when the first valid analysis
arrived, producing a spurious overload response. Startup now awaits the initial
sweep before serving. Later five-minute sweeps still acquire the shared slot and
wait for active work. A deterministic test verifies startup completion and
exclusion while another task owns the slot.

## Evidence and release limitations

See the repository's B13 implementation diff for executable fixtures and the
acceptance runner. Validation results below distinguish simulated boundaries
from native integrated acceptance; passing one does not imply the other.

- Python suite: 335 tests passed, including 12 B13 scenarios/boundary checks;
  one existing AnyIO deprecation warning.
- Frontend contract suite: 5 passed. Production Angular compilation passed.
- Existing Playwright browser suite with mocked API: 9 passed.
- PHP 8.3 syntax checks passed for the platform source and tests.
- Independent PHP B13 validation: 2 tests, 4 assertions passed.
- Additional Laravel checks using temporary PGlite/socket instead of native
  PostgreSQL: 27 tests, 243 assertions passed with the existing deliberate SQL
  error/atomic rollback test excluded. The full fallback run hit an aborted
  transaction in that test and contaminated subsequent tests. Do not infer native
  rollback correctness or failure from this alternative backend.
- Native Docker/Compose acceptance passed on Windows with Docker Desktop 28.0.1
  and Compose v2.33.1: `python scripts/verify-mvp.py` ran 28 Laravel tests
  (248 assertions) against PostgreSQL, verified all eight healthy services and
  their boundaries, passed three real Playwright browser scenarios (persisted
  success, escaped XSS and malformed output), and removed its disposable project
  and volume. The runner resolves the `npm.CMD` path on Windows before launching
  the browser suite.

The native PostgreSQL and isolated Compose browser gates above now pass. A prior
diagnostic host attempt using PGlite, real Redis/Laravel/worker/FastAPI and a
temporary Node proxy failed its browser acceptance (initial completion
timeout followed by API errors); it is not evidence of a passing full flow. The
AI pipeline did produce a valid success event, which does not prove successful
public reads/persistence. PGlite/socket also reproduces failed savepoint recovery
after an extended/prepared SQL error in a minimal PDO probe, whereas the same
probe with a simple query recovers. These alternatives are not committed runtime
dependencies and do not replace native PostgreSQL/Nginx/Compose verification.

No real LLM call, paid model evaluation, private repository, repository execution, source
modification or public deployment occurred. B14 navigation remains out of scope.
