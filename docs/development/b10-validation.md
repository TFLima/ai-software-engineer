# B10 AnalysisOrchestrator integration

Branch: `feat/mvp-0.1-b10`, based on `origin/feat/mvp-0.1-b09`.

The authenticated FastAPI endpoint now calls a fixed, injected orchestrator:
RepositoryReader → FileSelector → ContextBuilder → bounded LLMClient →
FindingValidator → cleanup. Laravel retains database ownership, independent
EnvelopeValidator checks, active-attempt/deadline fences, and transactional
findings/attempt/completed persistence from B04. There is no Python database,
queue, tool loop, schema repair, or runtime fake-provider fallback.

The reader instance survives requests, retaining GitHub quota cooldowns. Each
run creates a fresh bounded provider client. Paid-call settings are checked
before acquisition. Missing configuration fails safely at request stage without
source/provider calls. All stages share the original deadline and monotonic
elapsed bound, reserve cleanup, and obey stage caps. Saturated timeout durations
are recorded at the configured ceiling so scheduling latency cannot invalidate
the failure envelope. Synchronous selection/context/validation also check elapsed
time; their existing inner loops enforce budgets.

Resolved SHA is reported to the orchestrator before archive download, preserving
it on timeout and acquisition failure. Coverage and trusted adapter/policy/usage
provenance survive later failures. Failed candidates never appear in envelopes.
Cancellation unwinds snapshot cleanup before releasing the service slot. Cleanup
errors follow RepositoryReader's existing safe logging policy; they alone do not
invalidate successful findings. Scheduled stale cleanup remains B12.

## Running locally

Compose now forwards the B08 provider settings only to the AI container.
Generation remains disabled by default. In the ignored local `.env`, supply the
settings documented in [B08](b08-validation.md), including the credential,
explicit enablement, exact data-policy acknowledgment, source disclosure
acknowledgment, pinned model and bounded monetary policy. Do not print `.env` or
expanded Compose configuration containing credentials.

Selected public source is transmitted to OpenAI when enabled. Review the B08
provider disclosure and account settings before enabling; B11's browser disclosure
is still pending. Restart/rebuild the service after changes:

```sh
docker compose up -d --build
```

Use the existing public submit/status/findings API via a local HTTP client.
The frontend analysis flow remains B11. Integration tests inject snapshot
transport and the fake adapter; fake results are never selected by production
configuration.

## Verification

- `PYTHONPATH=services/ai python -m pytest services/ai/tests -q`: 317 passed;
  one existing AnyIO alias deprecation warning.
- `python -m compileall -q services/ai/app services/ai/tests`: passed.
- `git diff --check`: passed.

Fixtures exercise the authenticated endpoint through all real components with
simulated GitHub transport and fake generation, valid nonempty/empty findings,
whole-candidate rejection, provider failure, sensitive-only context, pinned SHA,
download failure, unexpected stage crash, cancellation, stage timeout, overall
expiry, and workspace removal. Existing regressions verify strict boundaries,
resource limits and provider budgets. No live GitHub or paid provider call ran.

`services/backend/tests/Fixtures/b10-success.json` was generated through the
Python orchestrator, not handwritten. The new Laravel feature test revalidates
that envelope, persists it, verifies public completion/results and duplicate
no-op behavior. Existing QueueHandoffTest fixtures cover rollback on second
finding insertion, crash/expiry reconciliation and stale-result fencing.
PHP, Composer and Docker are absent on this host, so the PostgreSQL-backed
Laravel suite and Compose integration could not run. Execute the existing local
stack's backend test procedure before considering cross-service runtime validation
complete. No real finding-quality or provider-cost measurement is claimed.
