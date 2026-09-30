# Initial limits and access policy — v1

These are initial conservative implementation defaults, not optimal or benchmarked values. They apply server-side before real acquisition/provider use. Central configuration is owned by Laravel; persist a frozen effective limits snapshot per attempt and pass relevant values to FastAPI. FastAPI also enforces local ceilings and rejects requests exceeding them; never silently raise budgets. Browser and repository content cannot override limits. Reject absent, non-finite, zero or negative configured values and inconsistent deadlines at startup. Override values require the same boundary checks; changing defaults requires updating this table and boundary fixtures. No configuration/runtime implementation is added in B01.

| Configuration key | Default | Measurement/enforcement and rationale |
| --- | --- | --- |
| `public_body_bytes` | 4096 | Entire JSON submission; only a repository URL is needed |
| `archive_bytes` | 20 MiB (20,971,520) | Actual streamed archive bytes per try; stop at limit, never trust Content-Length |
| `download_bytes` | 50 MiB (52,428,800) | All GitHub response bodies across retries in one attempt; bounds repeated transfer |
| `extracted_bytes` | 100 MiB (104,857,600) | Actual uncompressed bytes of all regular entries, including excluded files |
| `file_count` | 2000 | All regular archive entries, not just eligible text; reject duplicate normalized paths |
| `path_depth` | 12 | Segments after wrapper removal; bounds nested paths |
| `path_characters` | 512 | Normalized relative path length |
| `file_bytes` | 1 MiB (1,048,576) | Every regular entry; oversized files fail snapshot, not silent skip |
| `archive_entries` | 4000 | All entries including directories; bounds metadata-only archives |
| `context_files` | 100 | Maximum files with included text |
| `context_bytes` | 256 KiB (262,144) | UTF-8 rendered repository context, including path/line labels |
| `context_spans` | 500 | Included line spans across all files; bounds evidence map |
| `context_tokens` | 12000 | Repository context portion of each prompt |
| `input_tokens` | 16000 | Entire prompt including system instructions and schema |
| `output_tokens` | 6000 | Maximum generated tokens per model try |
| `attempt_tokens` | 44000 | Sum of input + reserved maximum output across model tries; up to 2 × 22000 |
| `max_findings` | 20 | Entire candidate; excess fails rather than truncates |
| `evidence_per_finding` | 5 | Array bound; at least one required |
| `internal_body_bytes` | 32768 | Entire internal run request including limits |
| `internal_response_bytes` | 1 MiB (1,048,576) | Streamed success/failure body; bounded before parsing |
| `active_analyses` | 1 | Global running analysis/attempt slot; local operator cost control |
| `queued_analyses` | 10 | Pending-slot cap: queued rows plus one reserved retry slot per running row; admission fails at cap, preventing a running failure from exceeding it |
| `outbound_concurrency` | 1 | GitHub/provider calls serialized within an invocation |
| `submissions_per_minute` | 6 | New admitted analyses in rolling 60 seconds; idempotent replay excluded |
| `connect_seconds` | 5 | Every outbound connect including TLS |
| `github_request_seconds` | 30 | Wall-clock entire logical network try, including streaming/DNS; no infinite inactivity extension |
| `provider_request_seconds` | 60 | Wall-clock per model try; fits two tries in stage budget |
| `github_requests` | 8 | Physical GitHub requests including redirects and retries per attempt |
| `redirects` | 2 | Per logical GitHub request; validate every hop/address |
| `acquire_seconds` | 75 | SHA resolution, download and safe extraction combined |
| `select_seconds` | 10 | FileSelector |
| `context_seconds` | 10 | ContextBuilder |
| `generate_seconds` | 125 | Model tries and backoff combined |
| `validate_seconds` | 10 | FindingValidator |
| `cleanup_seconds` | 10 | Reserved cleanup budget; cleanup failure logged safely and scheduled for stale cleanup |
| `overall_seconds` | 240 | From Laravel claim; includes transit, stages, waits and cleanup |
| `worker_http_seconds` | 255 | Longer than AI deadline for error/cleanup delivery |
| `job_seconds` | 270 | Longer than HTTP timeout |
| `attempt_lease_seconds` | 285 | Reconciliation takeover only after job deadline |
| `redis_reservation_seconds` | 300 | Longer than job and lease; avoids premature redelivery |
| `reconcile_seconds` | 30 | Reconciliation interval and minimum due queue republish age |
| `operation_tries` | 2 | One retry per logical GitHub/provider operation |
| `operation_backoff_seconds` | 1 | Initial retry wait; Retry-After may increase only within deadline |
| `automatic_attempts` | 2 | Initial plus one automatic transient retry |
| `total_attempts` | 3 | Includes at most one later operator retry |
| `attempt_backoff_seconds` | 5 | Wait before automatic next attempt |

Stage budgets total 240 seconds; they are upper bounds, not guaranteed allocations. Each stage uses the smaller of its budget and remaining overall time, reserving 10 seconds for cleanup until cleanup starts. Reject an already expired request. Strict ordering: `overall < worker_http < job < attempt_lease < redis_reservation`. All execution retries/waits consume attempt budgets. Queue waiting has no execution deadline and consumes no attempt; expose queue age and reconcile rather than calling it a running timeout.

Use the configured model's tokenizer when available. Otherwise conservatively count each UTF-8 byte as one token for admission (including full prompt overhead); never estimate characters divided by four. Reject configuration if the model context window cannot hold input plus output. Reserve input + maximum output against attempt budget before each model try even if the prior try's usage was lost. Usage returned may be null where unavailable; unknown usage does not restore reservations. Paid-call monetary budgets and provider data-use/retention remain required B08 decisions before enabling real calls.

Archive limits reject the snapshot; do not continue with a partially extracted repository. Context limits permit deterministic omissions with coverage reasons, but empty eligible context fails `no_eligible_context`. Evidence map limits must be applied while constructing context, not by later dropping spans. Application queue/concurrency policies must be checked atomically; serialize attempt claims globally. FastAPI accepts at most one run at a time; overload returns `upstream_unavailable`. In an ambiguous timeout an old invocation may still unwind; a new run must respect that slot and stale fencing. Container CPU/memory settings belong to B02 and must support these bounds.

## Network and access scope

MVP 0.1 is single-operator on the local machine. Bind only Nginx to `127.0.0.1` (and optionally `::1`); never `0.0.0.0` or LAN/public addresses. No multi-user authentication, tenancy, internet hosting, mobile/cloud exposure or public deployment is authorized by these contracts. A later access-control ADR is required for wider scope.

Angular calls only same-origin Laravel routes. Restrict API Host and Origin to configured loopback origins, disable cross-origin access, require JSON submissions and the idempotency header, and reject unexpected origins (including `null`). A non-browser local client may omit Origin but must use the allowed Host. Loopback binding is not protection against other local processes; it is the explicit single-operator trust assumption.

Keep FastAPI, Redis and PostgreSQL on the private service network with no host-published ports. Internal run requests require a runtime bearer secret (see [internal API](internal-api-v1.md)); the frontend never receives it. FastAPI has no PostgreSQL credentials. Do not route `/internal` through Nginx.

RepositoryReader constructs fixed HTTPS endpoints on `api.github.com` for public metadata/default-head resolution and `codeload.github.com` for the SHA archive. No arbitrary URL fetcher. TLS verification required; check DNS/address and redirect targets on every connection, block private/loopback/link-local/reserved destinations and enforce exact host allowlists. Redirects cannot introduce credentials, custom ports or non-HTTPS schemes. Public source cannot select endpoints; no submodule/LFS/source URL fetches. LLM network access is only to the trusted configured provider adapter endpoint, never a source-controlled endpoint. Do not execute any repository content.
