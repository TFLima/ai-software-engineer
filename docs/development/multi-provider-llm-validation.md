# Multiprovider LLM configuration and validation

Implementation date: 2026-10-18. Base: `origin/main` at `8b58fb3` (B14).
Branch: `feat/mvp-0.1-multi-provider-llm`. No merge to main.

## Architecture and compatibility

`llm_factory.llm_client_from_env` is the only runtime selection point. The
orchestrator default factory changes; its stages, public/internal schemas,
Laravel persistence, ContextBuilder and FindingValidator remain unchanged.
Missing `LLM_PROVIDER` preserves OpenAI with the previous fail-closed policy.
Unknown/blank selections fail `configuration_error`; no fallback exists on
configuration, transport or output failure. Provider/model provenance uses the
existing envelope and database fields; Laravel's EnvelopeValidator accepts these
bounded strings independently of the provider.

OpenAI retains the reviewed pinned model `gpt-4.1-mini-2025-04-14` and legacy
`LLM_*` configuration. Optional nonempty `OPENAI_*` settings take precedence over
the corresponding legacy names: MODEL, CONTEXT_WINDOW, DATA_POLICY,
SOURCE_DISCLOSURE_ACKNOWLEDGED, INPUT_MICROUSD_PER_MILLION,
OUTPUT_MICROUSD_PER_MILLION, CALL_MICROUSD and ATTEMPT_MICROUSD.
`OPENAI_MAX_OUTPUT_TOKENS` can lower its 32768 model output ceiling.
No arbitrary OpenAI model is admitted; adding another reviewed profile requires
code/tests, avoiding silently incorrect capabilities or prices.

Anthropic implements the same ModelAdapter contract without an SDK. It sends
Messages to fixed `https://api.anthropic.com/v1/messages`, using `x-api-key` and
`anthropic-version: 2023-06-01`. System instructions are separate from the
JSON-encoded untrusted source user message. No tools, thinking, caching requests,
URLs selected by source, navigation or execution are enabled. Verified TLS,
redirect rejection, response byte limits, connect/read/wall timeouts and safe
errors mirror OpenAI. Only BoundedLLMClient retries transient errors, reserving
full tokens/cost anew, within the existing deadlines and operation caps. Auth,
configuration, malformed output, refusals and truncation are terminal.

`output_config.format` requests structured JSON. Anthropic does not accept all
numeric/string/array bounds, so the adapter translates only unsupported schema
constraints into descriptions; closed objects, types, alternatives and enums
remain. It never transforms the returned candidate. B09 enforces EVERY original
constraint and exact context evidence, including case-sensitive enums. Invalid
JSON, duplicate keys, incomplete output or unknown fields reject the candidate;
there is no repair call. Envelope usage is translated to ModelReply; cache-read
tokens count as input without discounts. Unexpected cache writes, tools and
premium service metadata are rejected. Unknown usage stays unknown after an
ambiguous failure. No prompts, source, keys or upstream error bodies are logged.

## Reviewed models and prices

Official sources consulted on **2026-10-18**:

- [Messages request/response](https://platform.claude.com/docs/en/api/messages/create)
- [Structured JSON and unsupported constraints](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Usage, retries and errors](https://platform.claude.com/docs/en/api/errors)
- [Anthropic standard prices](https://platform.claude.com/docs/en/about-claude/pricing)
- [Haiku 4.5](https://platform.claude.com/docs/en/models/haiku-4-5/overview)
- [OpenAI pinned model and prices](https://developers.openai.com/api/docs/models/gpt-4.1-mini)
- [Anthropic commercial retention](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data)

| Provider model | Context ceiling | Output ceiling | USD/million input | USD/million output |
| --- | ---: | ---: | ---: | ---: |
| OpenAI gpt-4.1-mini-2025-04-14 | 1047576 | 32768 | 0.40 | 1.60 |
| Anthropic claude-haiku-4-5-20251001 (default) | 200000 | 64000 | 1.00 | 5.00 |
| Anthropic claude-sonnet-4-5-20250929 | 200000 | 64000 | 3.00 | 15.00 |

Prices are published standard API rates, not quality scores, negotiated rates,
cache discounts or billing guarantees. OpenAI's existing reviewed rates remain
unchanged from B08. Recheck official prices and model availability before paid
use. Local v1 caps (16000 input / 6000 output) remain much smaller. Anthropic
window/output configuration may lower the reviewed ceilings, but must hold the
frozen request caps. Unknown model IDs fail closed. One UTF-8 byte per token
counts source; the entire serialized payload/schema plus 1024 framing tokens
bounds Anthropic input conservatively. No extra token-count paid request exists.
Actual usage above reservations fails closed. Real token accounting/latency,
including structured-output framing, still needs homologation.

All prices/budgets use integer micro-USD ($1 = 1000000 micros). Reservations use
integer ceiling division. Default call and attempt ceilings remain 20000/40000.
`LLM_CALL_CEILING_MICROUSD` and `LLM_ATTEMPT_CEILING_MICROUSD` explicitly authorize
higher ceilings; changing provider budgets alone cannot raise them. Provider
budgets must fit those ceilings, and call must not exceed attempt. Rates below
reviewed profiles are rejected. No environment setting changes token/deadline,
retry or Laravel lifetime-attempt limits.

**Important:** 6000 Haiku output tokens alone reserve $0.03, so original $0.02
call budgets intentionally reject generation before transport, even on tiny
repositories. Use an explicitly reviewed larger budget as below, or lower the
frozen server-side token limits coherently. No automatic token truncation occurs.
With $0.05/$0.10 configured, up to three Laravel attempts could reserve $0.30;
the comparison script performs one attempt per provider, each with up to two
operation tries. Reservations are not refunded on error or unknown usage.

## Setup and paid-call gates

Create an API key in the provider's developer console, with appropriate account
billing and project permissions:
[OpenAI API keys](https://platform.openai.com/api-keys) or
[Anthropic console](https://console.anthropic.com/). Chat subscriptions are not
API credentials or an API budget. Put keys in your local secret environment,
never in Git, logs, browser code or a command that prints environment values.
The Python process does not auto-load `.env`; Compose injects the example names
into **only** the AI service. Do not print `docker compose config` with real keys.

OpenAI: retain the `.env.example` legacy model, rates and budgets, configure
`OPENAI_API_KEY`, and after reviewing policy explicitly set
`LLM_REAL_ENABLED=true` and `LLM_SOURCE_DISCLOSURE_ACKNOWLEDGED=true`.
`LLM_DATA_POLICY=standard-abuse-monitoring-30d` acknowledges the existing OpenAI
policy. `LLM_PROVIDER=openai` selects it; absence has the same behavior.

Claude example, after separate policy review and budget approval:

```dotenv
LLM_PROVIDER=anthropic
LLM_REAL_ENABLED=true
ANTHROPIC_API_KEY=<inject-secret-locally>
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_CONTEXT_WINDOW=200000
ANTHROPIC_MAX_OUTPUT_TOKENS=64000
ANTHROPIC_DATA_POLICY=anthropic-standard-30d-exceptions-reviewed
ANTHROPIC_SOURCE_DISCLOSURE_ACKNOWLEDGED=true
ANTHROPIC_INPUT_MICROUSD_PER_MILLION=1000000
ANTHROPIC_OUTPUT_MICROUSD_PER_MILLION=5000000
# Explicit increase from conservative defaults; integer micros only.
LLM_CALL_CEILING_MICROUSD=50000
LLM_ATTEMPT_CEILING_MICROUSD=100000
ANTHROPIC_CALL_MICROUSD=50000
ANTHROPIC_ATTEMPT_MICROUSD=100000
```

Recreate the AI container after changing its injected configuration:
`docker compose up -d --build ai`. Then submit a bounded public repository via
the existing Angular flow and review model/provider provenance and evidence.
Changing `LLM_PROVIDER` alone never authorizes paid use or accepts a policy.
Anthropic ignores the OpenAI/legacy disclosure acknowledgement; its own policy
and boolean are mandatory. To select Sonnet, set its reviewed ID, rates to
3000000/15000000, and explicitly budget for its larger reservation (at the full
16000/6000 caps, up to 138000 micros per try before two tries). Do not copy Haiku
prices to Sonnet. No automatic provider or model fallback exists.

Fake runtime requires ALL of `LLM_PROVIDER=fake`, `LLM_ENVIRONMENT=test` or
`development`, `LLM_FAKE_ENABLED=true`, and `LLM_REAL_ENABLED=false`. Default
runtime environment is production; do not use fake to represent real analysis
quality. Tests may still inject fixtures directly. The isolated acceptance
entry point remains separate and explicitly disables real calls and both keys.

## Privacy and retention

Source filtering is imperfect. Selected public code, paths and line numbers
leave the machine when real generation is enabled. Confirm the account's
applicable terms, data-sharing settings, model and exceptions before either
provider's acknowledgement. Anthropic standard API retention is ordinarily up
to 30 days, with exceptions for agreement, legal and safety/policy obligations;
flagged violations can be retained longer. Structured-output grammar caching has
its own lifecycle. This implementation does not claim zero retention or that
OpenAI `store=false` applies to Anthropic. OpenAI's B08 policy remains applicable
to that adapter. The UI describes the configured external provider generically
and requires submission acknowledgement; the operator must disclose its actual
selection and policy. No new public configuration endpoint was introduced.

Local `ANALYSIS_RETENTION_DAYS` deletes local terminal analyses, not provider
records. Local deletion cannot erase provider-side data. See B12 operations.

## Reproducible homologation — PENDING, no paid calls executed

1. Check out this feature commit. Install this platform's AI requirements.
2. Review a small public target repository and record one immutable SHA. Never
   execute its code or dependencies. Use the same URL/SHA and v1 limits for both.
3. Independently configure both providers' keys, acknowledgements, rates and
   budgets, including explicit global ceilings as needed. Load the settings into
   the process environment privately. Confirm both accounts' balances/limits.
4. Only after explicit paid authorization run from repository root:

```sh
python scripts/compare-llm-providers.py \
  --repository https://github.com/octocat/hello-world \
  --commit 7fd1a60b01f91b314f59955a4e4d4e80d8edf11d \
  --output /tmp/llm-provider-comparison.json --allow-paid
```

The example is a plumbing smoke test, not representative quality evaluation.
The script validates both configurations before network access, uses the normal
pipeline and independently acquires the same pinned commit, performs no database
writes, and records provider/model, usage, integer estimated cost, elapsed time,
validated finding count and safe errors. Unknown usage produces null cost.
It refuses to run without `--allow-paid`. Inspect accepted findings separately
in a normal authorized application run; the report intentionally excludes raw
source, prompts, keys and finding text. Record the feature commit with the report.
Manually review semantic evidence, false positives, omissions and usefulness;
structural validation alone cannot prove them. Record startup/grammar latency,
retry ambiguity, coverage omissions and any rate-limit failures. Real provider
quality, latency, billing and comparative evaluation remain pending.

## Validation record

All automated provider requests used httpx.MockTransport or injected fake;
no paid LLM request was sent. Dependencies installed belong to this trusted
platform, never analyzed input repositories.

| Command/check | Result |
| --- | --- |
| `cd services/ai && python -m pytest -q -p no:cacheprovider` | 403 passed; existing AnyIO deprecation warning |
| `cd services/frontend && npm test` | 6 passed |
| `cd services/frontend && npm run build` | Passed |
| `cd services/frontend && node --test tests/browser.test.mjs` | 10 passed after installing Chromium |
| `python -m compileall -q services/ai/app services/ai/tests scripts/compare-llm-providers.py` | Passed |
| Comparison CLI without `--allow-paid` | Refused with exit 2 before calls, as required |
| Laravel/PHP and native Compose acceptance | Not run: PHP, Composer and Docker absent on this host; no Laravel implementation changed |

An initial Python invocation from repository root failed import collection;
rerunning from the documented `services/ai` directory passed. An initial browser
suite could not launch because Chromium was missing; after installing it via
`npx playwright install chromium --only-shell`, all 10 browser tests passed. No test assertion was weakened.

Coverage includes provider/default selection; explicit fake gates; invalid or
missing config/key/consent; real-provider failure without fallback; successful
Messages translation and provenance; JSON/schema/local evidence validation;
response size, usage/token/cost bounds; 429/5xx/auth/timeout/network mappings;
retry reservations and attempt exhaustion; injection as data, no tools and safe
logs; all existing Python/OpenAI regressions. External API compatibility remains
mock-verified until authorized real homologation.

## Changed files

- `.env.example`, `compose.yaml`, `compose.acceptance.yaml`: provider configuration, credentials confined to AI, safe defaults and isolated acceptance gates.
- `services/ai/app/llm_factory.py`: centralized selection.
- `services/ai/app/anthropic_llm.py`: reviewed config, schema, transport and usage translation.
- `services/ai/app/llm_client.py`: explicitly configurable monetary ceilings; integer budget enforcement retained.
- `services/ai/app/openai_llm.py`: compatible aliases and output ceiling configuration.
- `services/ai/app/orchestrator.py`: default composition factory only.
- `services/ai/tests/test_multi_provider.py`: deterministic regression/security/transport tests.
- `services/frontend/src/app.html`: accurate multiprovider disclosure, unchanged submission flow.
- `scripts/compare-llm-providers.py`: opt-in pinned-SHA paid comparison procedure.
- `README.md`, `docs/architecture/overview.md`, ADR index, ADR 0007 supersession note and ADR 0008: scope and decision documentation.
- This validation record: setup, sources, budgets, evidence and pending gates.
