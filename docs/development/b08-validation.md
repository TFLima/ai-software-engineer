# B08 LLMClient

B08 implements an independent platform-owned `LLMClient.generate(request)`
interface, `BoundedLLMClient`, one `OpenAIAdapter`, and `FakeLLMAdapter`.
The base is `origin/feat/mvp-0.1-b07`, commit
`5decb89f90c18f47d4e6a1c197d305523e621b42`; remote references were refreshed and
no later remote branch contained B07. Work is on `feat/mvp-0.1-b08`.

`GenerationRequest` takes B07's `ContextResult`, its resolved SHA, a frozen
effective v1 limits dictionary and an aware overall deadline. Results preserve
that exact context/coverage object and SHA, returning candidate JSON, trusted
provider/model, policy/schema provenance, aggregate usage and reservations.
Sensitive fields are excluded from object representations. There are no database
writes or endpoint changes. B09 will validate candidates and evidence; B10 will
integrate the components and centrally owned attempt policy. Do not add provider
settings to the closed v1 internal envelope or let repository content select them.

## Provider choice and disclosure

The selected adapter uses OpenAI's fixed HTTPS Chat Completions endpoint,
`gpt-4.1-mini-2025-04-14`, with a 1,047,576-token model window and 32,768-token
model output ceiling. The platform's much smaller v1 limits still apply.
This pinned, non-reasoning model supports structured outputs and makes cost
reservations straightforward. It is an initial operational choice, not evidence
of finding quality or a quality comparison with other models.

Official documentation checked on 2026-10-07:

- [Model capabilities, snapshot and pricing](https://developers.openai.com/api/docs/models/gpt-4.1-mini).
- [Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).
- [Structured output constraints](https://developers.openai.com/api/docs/guides/structured-outputs).
- [Provider data controls](https://developers.openai.com/api/docs/guides/your-data).

**Selected public source code, relative paths and original line labels are sent
to OpenAI when real generation is enabled.** B06 filtering is imperfect and does
not guarantee removal of secrets. Repository instructions remain source data in
a separate JSON-encoded user message; only platform policy enters the system
message. The model cannot execute repository code or choose any action.

The request sets `store=false`, requests only text, and uses no tools, files,
audio, background processing or conversations. OpenAI's published API policy
excludes training by default unless the customer opts in. Standard abuse
monitoring may retain customer content for up to 30 days, with applicable legal
exceptions. `store=false` is an application-state setting, **not a zero-retention
guarantee**; provider prompt caching also has its own documented retention.
Zero Data Retention and Modified Abuse Monitoring require provider approval and
organization/project configuration; this adapter does not claim either is
configured. Before enabling, the operator must verify account data-sharing
settings and acknowledge the documented standard policy and source disclosure.
The B11 UI disclosure remains future work.

## Schema and provider boundary

The platform constructs the v1 finding schema with frozen finding/evidence caps.
Strict JSON output uses a nested `anyOf` between finding objects with and without
confidence, preserving omission and never converting missing confidence to null.
Every variant is closed and its own properties are required. Relational evidence,
trimmed text/control-character rules and full candidate validation remain B09.

The adapter bounds streamed response bytes before parsing the provider envelope,
rejects invalid UTF-8/JSON, duplicate keys, non-finite numbers, unknown envelope
fields, unexpected models/tiers and unsolicited tool output. Supported usage
detail metadata is validated but not exposed as candidate fields. The candidate
string is returned unchanged, even if it is malformed JSON or contains unsupported
fields: B08 never repairs, strips fences, filters fields or makes another model
call to fix output. A refusal, truncated output or blank content instead yields
terminal `invalid_findings`, preserving available usage. No upstream body,
exception message, source, prompt, candidate or credential is logged.

## Limits, pricing and retries

No compatible model tokenizer is installed. Admission uses the normative
conservative fallback: one UTF-8 byte per token. B07 can use
`adapter.context_tokens`; B08 independently recounts context and counts the
entire serialized provider request, including schema, system/user messages and
configuration, plus 256 tokens for framing. It rejects oversized input rather
than truncating or rebuilding context. A configured window must hold the full
input/output caps. Shared limit types, ceilings and relational consistency are
checked independently for direct component callers.

Standard prices checked above are $0.40 per million input tokens and $1.60 per
million output tokens. `service_tier=default` requests standard pricing. Cached
input discounts are never assumed. The integer monetary policy uses micro-USD,
rounding each reservation upwards. Default/local ceilings are **$0.02 per call
and $0.04 per generation attempt**, including retries. With v1 maxima, each try
reserves at most $0.016 and two tries at most $0.032. Rates below the checked
prices and budgets above the local ceilings are rejected; rates may be raised
and budgets lowered. Recheck prices before enabling paid use; these estimates
are controls based on configured prices, not a provider billing guarantee.

Each try reserves complete counted input plus **maximum** output tokens and the
corresponding cost **before** transport starts. Successful, failed and ambiguous
calls keep their reservations; reported zero usage does not refund anything.
Unknown usage stays null independently for each aggregate counter. Results and
safe errors expose the reservation ledger. Each `generate` invocation represents
one generation stage of one attempt; callers must not invoke it repeatedly to
reset the ledger. New execution-attempt allocation and the lifetime three-attempt
cap remain Laravel/B04 responsibilities. At these ceilings three attempts could
reserve up to $0.12; no unbounded retries are authorized.

Provider calls are serialized within a client; overlapping generation fails
without a second call. The runtime adapter has no SDK and no transport retries;
redirects are disabled, TLS is verified and the endpoint is fixed. Connect is
bounded by `connect_seconds`; an async wall timeout covers the entire try,
including connection and streamed reads. Generation uses the smaller of its
monotonic stage budget and propagated absolute deadline, reserving cleanup time.
The defaults are a 5-second connection, 60-second try, 125-second generation
stage, two tries and 1-second backoff.

Network failures, 408/504, 429 and other 5xx map to the safe transient codes.
Credential/configuration failures and invalid output are terminal. A retry occurs
only if backoff/Retry-After plus a full next try fit the remaining stage/deadline,
and a fresh token/cost reservation succeeds. There are no schema-repair retries.
Initial limits remain conservative: simulated measurements validate enforcement,
not real latency, quality or optimal budgets. Tune only after a separately
authorized, bounded real-provider evaluation.

## Configuration and fake usage

`.env.example` supplies all standalone settings without credentials. Real calls
are disabled by default. `openai_client_from_env()` requires explicit
`LLM_REAL_ENABLED=true`, `OPENAI_API_KEY`, the pinned `LLM_MODEL`, exact
`LLM_CONTEXT_WINDOW`, `LLM_DATA_POLICY=standard-abuse-monitoring-30d`,
`LLM_SOURCE_DISCLOSURE_ACKNOWLEDGED=true`, both pricing rates and both monetary
budgets. Missing/invalid settings raise only `configuration_error`; no silent
fake/provider fallback occurs. Environment values are not auto-loaded from a
file, and the credential generator preserves existing `.env` files. Inject these
settings into the standalone Python process using the operator's secret manager
or shell. Compose does not pass provider credentials yet and the internal
endpoint continues to fail safely until B10.

Fake use needs no credentials or network. From `services/ai`, after installing
`requirements-dev.txt`, the following executable fixture exercises generation:

```python
import asyncio
from datetime import datetime, timedelta, timezone
from app.context_builder import ContextResult, Coverage, IncludedSpan
from app.fake_llm import FakeLLMAdapter
from app.llm_client import BoundedLLMClient, GenerationRequest, ModelReply, Usage
from app.limits import CEILINGS

text = 'FILE "app.py"\n1: pass\n'
coverage = Coverage(1, 1, 1, 1, 0, (IncludedSpan("app.py", 1, 1),), (),
                    ("Static inspection of selected context only",))
context = ContextResult("1", text, len(text.encode()), len(text.encode()), coverage)
request = GenerationRequest(context, "a" * 40, dict(CEILINGS),
                            datetime.now(timezone.utc) + timedelta(seconds=240))
fake = FakeLLMAdapter([ModelReply('{"schema_version":1,"findings":[]}', Usage(100, 20))])
result = asyncio.run(BoundedLLMClient(fake).generate(request))
assert result.candidate_json == '{"schema_version":1,"findings":[]}'
assert result.reservations.tries == 1
```

Configure any raw candidate with `ModelReply`, including valid nonempty, empty or
invalid JSON. Configure failure sequences with safe `LLMError` objects, e.g.
`[LLMError("upstream_unavailable"), ModelReply(...)]`. Tests inject
`httpx.MockTransport` into the real adapter to verify request/response behavior
without sending source or paying for a call. Fake candidates are not validated
findings and must never be persisted without B09.

## Validation record

Python 3.12 virtualenv `/tmp/b08-venv` was created and the repository's development
requirements installed. The host Python initially lacked pytest. The restricted
sandbox stalled existing threaded ASGI/transport tests; interrupted those runs
and reran the complete suite with the command's sandbox network permission.
All provider tests still used simulated transport, not a live provider.

| Check | Result |
| --- | --- |
| `python -m pytest -q -p no:cacheprovider tests/test_llm_client.py` | 77 B08 tests passed in the final suite |
| `python -m pytest -q -p no:cacheprovider` in `services/ai` | 248 passed, including all 171 B04–B07 regressions; one existing AnyIO alias deprecation warning |
| `python -m compileall -q app tests` | Passed |
| `git diff --check` | Passed |

Fixtures cover B07 compatibility/provenance, schema translation, optional
confidence, untrusted instructions, fake and real-adapter valid/empty/invalid
candidates, refusal/truncation, missing configuration/credentials, full-prompt
admission, monetary rounding/caps, reservations across retries and unknown usage,
safe status/transport errors, deadline/stream cancellation, response-byte limits,
closed provider envelopes and duplicate keys, no tools, concurrency and log/repr
exclusion. No live GitHub request, paid provider call, Docker/Compose build,
finding-quality evaluation, B09/B10 integration or frontend work was performed.

B08 component implementation and deterministic validation are complete. Real
account permissions, provider acceptance of the schema and real cost/latency
remain unverified. These are not claimed by simulated tests; real calls remain
disabled until the documented operator settings are supplied.
