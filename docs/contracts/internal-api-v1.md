# Laravel → FastAPI run contract — v1

`POST /internal/v1/analyses:run` is a synchronous call inside an asynchronous Laravel job. No Python queue, callback, database write or browser access. Require JSON, runtime `Authorization: Bearer <secret>` and a 32 KiB request cap. Authenticate before executing any stage. Missing/invalid secret returns 401; safe fixed error code `unauthorized_internal`, no upstream work. Secret comparison must be timing-safe; never log/store the header. Runtime secret is shared only by worker/service, not source/model/frontend. Private networking and no edge routing are additional requirements, not substitutes for authentication.

## Request envelope

All fields below required, including nullable `commit_sha`. `schema_version` and `finding_schema_version` must equal integer 1. Repository object is exactly `{owner,name,url}`, matching the public canonicalization; service revalidates it. IDs must be valid UUIDs; `attempt_number` integer 1–3. `deadline_at` is Laravel claim time plus 240 seconds, never extended in FastAPI. On receipt require nonexpired UTC deadline at most configured overall seconds into the future; enforce monotonic local elapsed timers plus the propagated absolute deadline. Deployment clocks must be synchronized; reject impossible/future-skewed deadlines as `invalid_request`.

`limits` is exactly the AI-relevant subset of central configuration shown in the example; all keys required, integers > 0, defaults/units in [limits](limits-and-access-v1.md). Validate relational consistency and configured ceilings before network work. Laravel-only limits are not passed. Server-owned versions are opaque exact strings `1` for initial prompt/selection/context policies, not model-selected identifiers; unsupported values reject as `unsupported_schema`.

```json
{
  "schema_version":1,
  "finding_schema_version":1,
  "analysis_id":"11111111-1111-4111-8111-111111111111",
  "attempt_id":"22222222-2222-4222-8222-222222222222",
  "attempt_number":1,
  "repository":{"owner":"example","name":"small-app","url":"https://github.com/example/small-app"},
  "commit_sha":null,
  "deadline_at":"2026-09-30T22:04:01Z",
  "selection_policy_version":"1",
  "context_policy_version":"1",
  "prompt_version":"1",
  "limits":{
    "archive_bytes":20971520,"download_bytes":52428800,"extracted_bytes":104857600,
    "file_count":2000,"path_depth":12,"path_characters":512,"file_bytes":1048576,"archive_entries":4000,
    "context_files":100,"context_bytes":262144,"context_spans":500,"context_tokens":12000,
    "input_tokens":16000,"output_tokens":6000,"attempt_tokens":44000,
    "max_findings":20,"evidence_per_finding":5,"internal_response_bytes":1048576,
    "outbound_concurrency":1,"connect_seconds":5,"github_request_seconds":30,"provider_request_seconds":60,
    "github_requests":8,"redirects":2,"acquire_seconds":75,"select_seconds":10,"context_seconds":10,
    "generate_seconds":125,"validate_seconds":10,"cleanup_seconds":10,"overall_seconds":240,
    "operation_tries":2,"operation_backoff_seconds":1
  }
}
```

SHA null means resolve default head once; non-null means inspect precisely that SHA for this repository. Success echoes the resolved SHA. Known SHA is retained even on later-stage failure. A new run always requires a fresh attempt ID; callers must not transparently retry this POST after an ambiguous response. FastAPI echoes IDs, never assigns Laravel IDs. [Lifecycle fencing](analysis-lifecycle-v1.md) is applied by Laravel regardless of transport status.

## Success envelope — HTTP 200

Closed object with exactly these fields. `outcome` is `succeeded`. `repository`, IDs and policy versions must match request; `commit_sha` is non-null and matches any requested SHA. Findings follow [schema v1](finding-schema-v1.md). No raw source, prompts or model output may be included.

```json
{
  "schema_version":1,
  "finding_schema_version":1,
  "analysis_id":"11111111-1111-4111-8111-111111111111",
  "attempt_id":"22222222-2222-4222-8222-222222222222",
  "outcome":"succeeded",
  "repository":{"owner":"example","name":"small-app","url":"https://github.com/example/small-app"},
  "commit_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "findings":[{
    "category":"reliability","severity":"medium","title":"Report write may leave partial state",
    "explanation":"The inspected sequence writes related records separately; failure between writes may leave inconsistent state.",
    "recommendation":"Consider a transaction around the related writes and verify failure behavior.",
    "evidence":[{"path":"app/Services/ReportService.php","start_line":10,"end_line":18}],"confidence":0.7
  }],
  "coverage":{
    "inventory_files":1,"eligible_files":1,"included_files":1,"included_lines":9,"omitted_files":0,
    "included_spans":[{"path":"app/Services/ReportService.php","start_line":10,"end_line":18}],
    "omissions":[],"limitations":["Static inspection of selected context only"]
  },
  "provenance":{
    "finding_schema_version":1,"selection_policy_version":"1","context_policy_version":"1","prompt_version":"1",
    "provider":"fake","model":"fixture-v1","usage":{"input_tokens":200,"output_tokens":100}
  },
  "stage_durations_ms":{"acquire":1000,"select":20,"context":30,"generate":500,"validate":20,"cleanup":10}
}
```

Coverage counts are nonnegative integers; `included_files <= eligible_files <= inventory_files <= file_count`; `omitted_files = inventory_files - included_files`. `included_lines` is the sum of inclusive spans; spans are sorted by path then line, unique, disjoint and merged when adjacent, capped at `context_spans`, with at most `context_files` unique paths. Success requires at least one included file/line. All paths/lines obey finding evidence rules. Included lines must be exactly those rendered in context; no source content is carried.

`omissions` is up to 16 closed `{reason,files}` summaries, unique per reason, with nonnegative integer counts summing to `omitted_files`. Reasons: `binary`, `generated`, `vendor`, `sensitive`, `unsupported_text`, `context_budget`, `submodule`, `lfs`. Partially included files count as included; describe omitted spans via limitations, not omitted_files. `limitations` is 1–16 plain-text strings of 1–256 characters describing static-only inspection, skipped dependencies, truncation and other coverage constraints without raw source. Directory-only submodules not represented as regular files are reported in limitations rather than inventing file counts.

Provenance is exactly the object shown; provider/model are trusted adapter identifiers of 1–128 characters. Usage values are nonnegative integers or null independently, aggregated across all tries; if any try's value is unknown, aggregate is null for that counter. This does not refund reserved budgets. Provenance schema version must agree with root. Durations object has exactly `acquire`, `select`, `context`, `generate`, `validate`, `cleanup`, nonnegative integer milliseconds or null when stage not reached; bounded by stage budgets. Use monotonic elapsed time including retries. Success requires all non-null durations; failure preserves reached stages.

## Failure envelope

All fields shown required. `outcome` is `failed`; `findings` is forbidden. SHA, coverage and provenance may be null when unavailable; non-null values use the success schemas. Error is exactly `{code,stage,retryable}` with no upstream message. Stage enum: `request`, `acquire`, `select`, `context`, `generate`, `validate`, `cleanup`, `transport`, `queue`. Last two are Laravel-generated errors, not FastAPI-returned stages. Codes and retryability follow the [lifecycle table](analysis-lifecycle-v1.md). Cleanup failure alone after otherwise valid generation does not invalidate findings: log safe metadata and arrange stale cleanup; acquisition/pipeline failure remains failure.

Example HTTP 502 (provider unavailable after bounded tries):

```json
{
  "schema_version":1,
  "finding_schema_version":1,
  "analysis_id":"11111111-1111-4111-8111-111111111111",
  "attempt_id":"22222222-2222-4222-8222-222222222222",
  "outcome":"failed",
  "repository":{"owner":"example","name":"small-app","url":"https://github.com/example/small-app"},
  "commit_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "coverage":{
    "inventory_files":1,"eligible_files":1,"included_files":1,"included_lines":9,"omitted_files":0,
    "included_spans":[{"path":"app/Services/ReportService.php","start_line":10,"end_line":18}],
    "omissions":[],"limitations":["Static inspection of selected context only"]
  },
  "provenance":{
    "finding_schema_version":1,"selection_policy_version":"1","context_policy_version":"1","prompt_version":"1",
    "provider":"fake","model":"fixture-v1","usage":{"input_tokens":null,"output_tokens":null}
  },
  "stage_durations_ms":{"acquire":1000,"select":20,"context":30,"generate":2000,"validate":null,"cleanup":10},
  "error":{"code":"upstream_unavailable","stage":"generate","retryable":true}
}
```

The failure example preserves known source/context/model provenance while usage remains unknown. If failure occurs before context construction, coverage may be null; before adapter selection, provenance may be null. Preserve known validated values whenever available; never fabricate failed-source metadata. HTTP mapping: 422 for invalid request/schema and terminal acquisition/policy/context/finding failures; 502 for network/upstream unavailable; 504 for upstream timeout; 503 for service concurrency overload; 429 for upstream rate limit; 500 for service configuration/internal invalid result. `outcome` determines result type, but status must agree with this mapping. FastAPI never returns 202.

Preflight rejection cannot always echo trustworthy IDs. Use the closed early error object `{schema_version:1,error:{code,stage:"request",retryable:false}}` for malformed JSON, oversize body, failed auth, unsupported version or invalid request. HTTP 400 malformed JSON, 413 body cap, 415 media type (all code `invalid_request`), 401 auth (`unauthorized_internal`), 422 schema (`unsupported_schema`) or request (`invalid_request`). Overload after valid request uses full failure with code `upstream_unavailable`, stage `request`, HTTP 503. Unauthenticated callers get only the early object. Laravel treats missing/malformed/non-JSON received responses as local `invalid_result` for the still-active invocation; a connection loss/timeout instead uses transient transport codes. Apply identity/deadline fences to local failures and never persist unvalidated response provenance.

## Invalid request/result examples

| Mutation of examples | Required behavior |
| --- | --- |
| Request `"schema_version":2` | 422 early error below; no version fallback or execution |
| Request adds `"tools":["shell"]` | 422 `invalid_request`, unknown field |
| Request `limits.archive_bytes = 0` or above local ceiling | 422 `invalid_request`, no work |
| Request URL is `http://localhost/repo` | 422 `invalid_request`, no fetch |
| Success carries a different attempt UUID | Laravel discards as stale/mismatched; no persistence |
| Success contains unsupported schema or unknown root field | Active matching attempt fails `invalid_result`, nonretryable |
| Success evidence exceeds included spans | Active matching attempt fails `invalid_result`, nonretryable |
| Failure claims `invalid_findings` with `retryable:true` | Protocol violation → local `invalid_result`, no automatic retry |

```json
{"schema_version":1,"error":{"code":"unsupported_schema","stage":"request","retryable":false}}
```

Laravel validates envelopes, preserves safe provenance, applies application IDs and commits findings plus completed state atomically. A legitimate failure never presents candidate findings. All error handling and logging must exclude source, prompts, bearer tokens and raw provider output.
