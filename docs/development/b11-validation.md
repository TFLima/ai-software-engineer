# B11 Frontend analysis flow

Branch: `feat/mvp-0.1-b11`, based on B10 commit `c76a3de`.

The Angular page replaces the infrastructure placeholder with the public analysis
flow. UI labels are Portuguese (pt-BR). Requests are relative, same-origin Laravel
routes; the browser never calls FastAPI, GitHub or the provider directly and never
receives credentials. Existing loopback scope and Host/Origin enforcement remain.

## Behavior

- Canonical public GitHub URL validation mirrors the public API, including `.git`
  and trailing slash handling. Private/inaccessible repository detection remains
  asynchronous on the server.
- The provider disclosure precedes submission: selected public code, paths and
  lines may go to OpenAI; sensitive filtering is imperfect; standard abuse
  monitoring may retain content for up to 30 days and `store=false` is not zero
  retention. An unchecked acknowledgment prevents submission. It is not a server
  field and cannot enable an unconfigured provider.
- Submission sends only `repository_url` plus the required JSON/Accept and
  Idempotency-Key headers. A canonical URL/key binding is kept in sessionStorage
  for ambiguous-response recovery in the same tab, including reload. Memory
  fallback works when storage is unavailable. Retrying the same canonical URL
  reuses its key; changing URL or explicitly choosing Nova análise uses a new key.
  Acknowledgment resets on reload/new analysis; no POST is retried automatically.
- A hash route `#analysis/<uuid>` identifies a read view. Reload/back/forward reads
  status; it never submits or allocates an execution attempt. Navigation cancels
  pending reads/timers. Status is fetched immediately, then after 2, 4, 8 and at
  most 10 seconds for queued/running states. HTTP requests time out at 10 seconds;
  requests never overlap. Terminal completed/failed statuses stop polling.
- Availability failures respect Retry-After, with at most five consecutive failed
  reads before pausing and offering explicit resume. Excessive status cooldowns
  above five minutes pause rather than overflowing browser timers. Submission
  cooldowns disable the button and do not automatically POST again.
- Completed results use immutable SHA and pages of five findings. Previous/next
  controls, requested-page retry and valid empty-result messaging are distinct
  from pending/failed states. Failed states never display successful empty results.
- Coverage includes inventory, eligibility, included files/lines, omissions and
  limitations. Provenance displays provider/model/prompt and known/unknown usage.
  Evidence shows relative paths and original inclusive line numbers at the SHA;
  source navigation/filtering remains B14.
- All findings, paths and limitations use Angular text interpolation. No innerHTML,
  Markdown rendering or raw response message is used. Confidence is labeled an
  uncalibrated model assessment. Empty findings never certify repository safety.

`src/api.ts` decodes closed public v1 responses, checks versions/identity/SHA,
counts/pagination, finding bounds/enums/paths, and metadata. Raw JSON rejects
nested/escaped duplicate keys, nonfinite numbers, excess depth and responses over
1 MiB before interpretation. Model output never enters browser code or links.
Errors use local actionable phrases by safe code; raw upstream output and exception
messages are not shown. Public coverage does not carry the internal evidence map;
Laravel remains authoritative for evidence validation/persistence.

The acknowledgment complements the existing operator provider settings; it is not
a substitute for server data-policy or monetary budgets. Operator execution retry
remains the existing controlled CLI, not a frontend retry endpoint.

## Validation

From `services/frontend`, run `npm test` for contract fixtures and
`npm run test:browser` for the production Angular build plus Chromium scenarios.
Install the pinned Playwright browser with `npx playwright install chromium
--only-shell`. An existing compatible system Chromium may be selected with the
`CHROMIUM_EXECUTABLE` environment variable. Node 22.18+ is required for the native
TypeScript contract tests. No test framework is shipped in the browser bundle.

Final results:

| Check | Result |
| --- | --- |
| `npm test` | 5 contract scenarios passed |
| `npm run build` | Production build passed; initial bundle approximately 167 KiB, below configured limits |
| `node --test tests/browser.test.mjs` | 9 Chromium scenarios passed |
| Desktop/mobile screenshot inspection | Passed; 390 px viewport has no horizontal overflow |
| `git diff --check` | Passed |

The initial browser download was unavailable for Playwright 1.62.1. The final
lockfile pins development-only Playwright 1.56.1; its Chromium 141 headless shell
installed from the official download mirror. System package installation did not
complete and is not a project prerequisite. Timing tests inspect actual scheduled
poll delays and API calls while advancing the browser clock, avoiding assumptions
that ordinary browser time stays frozen between interactions.

Browser fixtures
use a loopback static server and intercepted public API responses. They test
admission consent, URL/headers, ambiguous-response idempotency/reload, cooldown,
queued/running/completed/failed, bounded polling and stop on navigation/terminal,
read recovery, pagination/retry, empty findings, XSS plain text, closed responses
and mobile width. No live repository/provider call or paid evaluation is made.

PHP, Composer and Docker are absent here. Full Compose/Laravel/PostgreSQL flow
and real-provider behavior remain pending; B13 integrated MVP verification is not
claimed by frontend fixtures. Real generation stays disabled by default.
