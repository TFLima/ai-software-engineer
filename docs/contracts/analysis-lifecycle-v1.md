# Analysis and attempt lifecycle — v1

Laravel alone mutates durable state. PostgreSQL is authoritative; Redis delivery is at least once. See [internal envelopes](internal-api-v1.md) and [limits](limits-and-access-v1.md).

## Analysis transitions

| From | To | Trigger and atomic precondition |
| --- | --- | --- |
| Absent | `queued` | Valid submission and new idempotency key; create durable row before publication |
| `queued` | `running` | Claim under row lock/compare-and-set; no active attempt; allocate new attempt ID/number and deadline |
| `running` | `completed` | Valid success for the active unexpired attempt; persist all findings and provenance in the same transaction |
| `running` | `queued` | Retryable attempt failure/expiry with remaining automatic allowance; close attempt and clear active ID atomically; set `next_attempt_at` |
| `running` | `failed` | Nonretryable failure or automatic allowance exhausted; close attempt and clear active ID atomically |
| `failed` | `queued` | Explicit controlled operator action; eligible transient failure and total attempt allowance remaining |

All other transitions are forbidden. `completed` is permanently terminal and immutable (status, successful attempt, findings, source and provenance). `failed` is terminal to automated execution; only the operator transition above may reopen it. Failed attempt records remain immutable. Policy/schema/validation failures cannot be reopened: a new submission with a new key is required after remediation. No cancellation or retry HTTP route exists in 0.1. Retention/deletion under B12 is separate from mutation of a retained result.

An analysis has zero attempts while initially queued, at most one active attempt while running, and monotonically increasing attempt numbers starting at 1. Queued retries retain previous attempt history but have no active attempt. Submission replay never retries an analysis. Public `error` describes the latest closed failure until a new claim clears it; public `commit_sha` is that of the latest attempt with known provenance, or null if the latest attempt has no known SHA. Completed uses the successful attempt only.

## Attempt transitions and fences

| From | To | Rule |
| --- | --- | --- |
| Absent | `running` | Allocate at claim; queued delivery itself is not an attempt |
| `running` | `succeeded` | Accepted valid success before persisted attempt deadline |
| `running` | `failed` | Valid failure or local protocol/policy error |
| `running` | `expired` | HTTP/job deadline lost or lease expiry; outcome is unknown, not successful |

Terminal attempts (`succeeded`, `failed`, `expired`) never reopen. Every new execution has a fresh UUID; never resend a run POST with the same attempt ID after an ambiguous transport failure. FastAPI need not keep durable deduplication state. Repository/network retries inside one invocation retain the same attempt ID and resolved SHA; resolving the default branch occurs once per attempt. A new attempt uses the previously recorded SHA if available; if a lost response makes it unavailable, resolve anew and record separate provenance. An explicitly supplied SHA must never fall back to a newer branch head.

On any result/error reception, Laravel locks the analysis and checks the identity/state fence: analysis ID matches, attempt belongs to analysis, status is `running`, active ID equals response attempt ID, attempt status is `running`, and deadline has not passed. Check again in the final persistence transaction. Do not hold a database lock during HTTP processing. A failing identity/state fence discards the response without changing results, provenance or status; safe metadata may be logged. For an active matching attempt, unsupported versions, a SHA differing from the pinned SHA, malformed success or invalid metadata become `invalid_result`, never partial success. A matching valid failure may record only known provenance.

Duplicate queue deliveries for running/completed/failed rows are no-ops. Delivery before `next_attempt_at` is a no-op. Competing claims must yield one winner. Duplicate accepted results and late results from expired/older attempts are no-ops, even if their findings differ. Finding IDs are Laravel-generated; use successful attempt plus array ordinal as persistence uniqueness, not model IDs.

## Retry policy and reconciliation

Only `network_unavailable`, `upstream_timeout`, `upstream_rate_limited`, `upstream_unavailable`, `attempt_expired` and `queue_unavailable` are transient codes. `queue_unavailable` affects publication, not a running attempt. `invalid_request`, `unsupported_schema`, `unauthorized_internal`, `repository_unavailable`, `unsafe_snapshot`, `limit_exceeded`, `no_eligible_context`, `invalid_findings`, `invalid_result` and `configuration_error` are nonretryable. Upstream 404/private/inaccessible repository maps to `repository_unavailable`; 429 maps to `upstream_rate_limited`; network/5xx use the transient set. Never expose upstream bodies.

Automatic execution: at most 2 attempts per analysis. An eligible transient first failure schedules one retry after 5 seconds; the second failure becomes `failed`. Operator retry allows at most one additional attempt (3 lifetime attempts total), without resetting counters; that third attempt gets no automatic retry. A retry uses a fresh overall deadline; source/provider calls may repeat and incur cost. Exactly-once execution is not promised. An internal failure's `retryable` boolean must match this code table; Laravel decides whether budgets permit retry.

Within an invocation, at most one retry per logical outbound operation (2 tries), with 1-second backoff; honor `Retry-After` only if wait plus next call fits the remaining stage/deadline, otherwise return the transient failure. All waits consume deadlines. No retries for invalid model output, policy breaches or authentication errors. Model tries are capped separately by the same limits; no schema-repair model call. Worker/queue framework automatic retry must not bypass durable attempt allocation/caps.

Reconciliation runs every 30 seconds: republish queued rows due for at least 30 seconds without successful claim (duplicate publication is safe); mark expired running attempts `expired` once their persisted lease expires; apply retry eligibility atomically. AI execution deadline is 240 seconds from claim, worker HTTP 255, job 270, attempt lease 285, Redis reservation 300. Reconciliation does not issue another attempt before the lease expires after a crashed worker. Explicit transport failure can close earlier after cancellation is requested; stale fencing still protects persistence if the old request continues. All external effects of old work are bounded by its original deadline.
