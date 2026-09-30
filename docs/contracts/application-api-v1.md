# Application API — v1

Laravel owns these routes. Content type is `application/json`; timestamps/UUIDs and closed-object behavior follow [shared conventions](README.md). Access is [single-operator loopback only](limits-and-access-v1.md). No user, tenant, credentials, branch, SHA or budget fields are accepted from the client in 0.1.

## POST /api/analyses

Require `Content-Type: application/json`, `Accept: application/json`, and `Idempotency-Key` of 1–128 ASCII characters matching `[A-Za-z0-9._:-]+`. Entire body <= 4096 bytes. Required sole field `repository_url`: nonempty string <= 2048 characters.

Accept only `https://github.com/{owner}/{repo}` with optional terminal `.git` and/or trailing slash. Owner: 1–39 ASCII alphanumeric/hyphen characters, beginning and ending alphanumeric, no consecutive hyphens. Repo: 1–100 ASCII alphanumeric, dot, underscore or hyphen characters; reject `.` and `..`. Reject percent escapes, whitespace, credentials, any explicit port, query/fragment, extra segments, alternate schemes/hosts. Host matching is case-insensitive; scheme must be HTTPS. Strip trailing slash then terminal `.git`; revalidate nonempty repo; lowercase owner/repo for canonical identity. Preserve no unvalidated input for acquisition. Public existence/access is verified asynchronously; syntactically valid inaccessible repos can still receive 202 and later fail.

```http
POST /api/analyses
Content-Type: application/json
Accept: application/json
Idempotency-Key: demo-analysis-001

{"repository_url":"https://github.com/Example/Small-App.git/"}
```

```json
{
  "schema_version": 1,
  "id": "11111111-1111-4111-8111-111111111111",
  "status": "queued"
}
```

Return HTTP 202 with `Location: /api/analyses/11111111-1111-4111-8111-111111111111`. New analysis, idempotency binding and queue-publication intent must be durable before return. Redis publication failure does not undo accepted analysis; reconciliation republishes. Database admission failure returns 503 without binding a key.

Idempotency is global in this single-operator instance. Use lowercase hexadecimal SHA-256 of exactly UTF-8 compact canonical JSON with sole field `repository_url`, after URL normalization (no whitespace, no escaping of `/`, no trailing newline). Persist key/hash/analysis binding atomically with a unique key constraint. Same key and normalized body returns the existing ID and **current** status, HTTP 202 and the same Location, even if completed/failed. Changed normalized body returns 409 `idempotency_conflict`; concurrent submissions obey the same rule. Different keys create different analyses even for the same URL. Invalid requests never bind keys. Keep bindings for the lifetime of retained analyses; B12 deletion must delete binding with analysis atomically, after which a reused key is new. Replay check follows syntax validation but precedes new-submission rate/queue caps; replay does not consume those caps or attempts. No provider-level idempotency guarantee is implied.

## GET /api/analyses/{id}

HTTP 200 response has exactly the fields shown. `repository` is exactly `{owner,name,url}` with canonical values. `status` is `queued|running|completed|failed`; `attempt_count` integer 0–3; active ID is non-null only while running. Nullable timestamps and source SHA represent unavailable values, not estimates. `started_at` is the first claim time; `finished_at` is the most recent terminal transition time, cleared when reopened. `created_at` is immutable. `coverage` and `provenance` are null until an accepted envelope supplies them; on retries they describe the latest closed attempt until the next claim clears them. `error` is null absent a failure, otherwise the safe object specified below. No stack trace, secret, prompt, workspace path or raw output is returned.

```json
{
  "schema_version": 1,
  "id": "11111111-1111-4111-8111-111111111111",
  "status": "completed",
  "repository": {"owner":"example","name":"small-app","url":"https://github.com/example/small-app"},
  "commit_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "attempt_count": 1,
  "active_attempt_id": null,
  "created_at": "2026-09-30T22:00:00Z",
  "started_at": "2026-09-30T22:00:01Z",
  "finished_at": "2026-09-30T22:00:20Z",
  "coverage": {"inventory_files":1,"eligible_files":1,"included_files":1,"included_lines":9,"omitted_files":0,"omissions":[],"limitations":["Static inspection of selected context only"]},
  "provenance": {"finding_schema_version":1,"selection_policy_version":"1","context_policy_version":"1","prompt_version":"1","provider":"fake","model":"fixture-v1","usage":{"input_tokens":200,"output_tokens":100}},
  "error": null
}
```

Public coverage is the [internal coverage](internal-api-v1.md) object **without** `included_spans` (bounded internal evidence map). Public provenance contains exactly the fields above; usage counters are nonnegative integers or null independently. Failed/queued-with-last-failure `error` has `{code,stage,message,retryable}`; code/stage/boolean follow internal/lifecycle definitions and message is a Laravel-owned safe phrase. `retryable` indicates error classification, not remaining retry entitlement. Counts/known metadata may be unavailable on failed analyses; do not fabricate them.

Queued initial example (HTTP 200):

```json
{
  "schema_version":1,
  "id":"11111111-1111-4111-8111-111111111111",
  "status":"queued",
  "repository":{"owner":"example","name":"small-app","url":"https://github.com/example/small-app"},
  "commit_sha":null,
  "attempt_count":0,
  "active_attempt_id":null,
  "created_at":"2026-09-30T22:00:00Z",
  "started_at":null,
  "finished_at":null,
  "coverage":null,
  "provenance":null,
  "error":null
}
```

## GET /api/analyses/{id}/findings

Only completed analyses return HTTP 200. Optional query fields: `page` decimal integer 1–2147483647, default 1; `per_page` integer 1–20, default 20. Unknown query fields or malformed integers yield 422. Sort by successful candidate ordinal ascending; stable immutable results. Each item is the [finding](finding-schema-v1.md) plus Laravel-owned UUID `id`. No filters in B01. Empty completed candidate returns `data:[]`, total 0, total_pages 0. Beyond-last page returns 200 with empty data and unchanged totals.

```json
{
  "schema_version":1,
  "analysis_id":"11111111-1111-4111-8111-111111111111",
  "commit_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "finding_schema_version":1,
  "data":[{
    "id":"33333333-3333-4333-8333-333333333333",
    "category":"reliability",
    "severity":"medium",
    "title":"Report write may leave partial state",
    "explanation":"The inspected sequence writes related records separately; failure between writes may leave inconsistent state.",
    "recommendation":"Consider a transaction around the related writes and verify failure behavior.",
    "evidence":[{"path":"app/Services/ReportService.php","start_line":10,"end_line":18}],
    "confidence":0.7
  }],
  "pagination":{"page":1,"per_page":20,"total":1,"total_pages":1}
}
```

Queued/running/failed analyses return HTTP 409 `analysis_not_completed`, never an empty successful findings result. Malformed or unknown path IDs return 404 `analysis_not_found` for either GET route. Polling clients start at 2 seconds, increase to max 10 seconds, and stop on terminal status or user navigation; admission/availability responses include Retry-After.

## Public error contract

Error root is exactly `{schema_version:1,error:{code,message,details}}`; `details` is an array of closed `{field,code}` objects, empty except validation. `message` is safe platform text, never upstream text. Common errors:

| HTTP | Code | Example trigger |
| --- | --- | --- |
| 400 | `invalid_json` | Malformed JSON/duplicate keys |
| 403 | `access_denied` | Unexpected Host/Origin |
| 404 | `analysis_not_found` | Unknown or malformed analysis ID |
| 409 | `idempotency_conflict` | Same key with different canonical body |
| 409 | `analysis_not_completed` | Findings requested before completed, including failed |
| 413 | `request_too_large` | Body exceeds byte cap |
| 415 | `unsupported_media_type` | Non-JSON content type |
| 422 | `validation_failed` | Invalid URL, unknown fields, missing/invalid key, invalid pagination |
| 429 | `admission_limited` | Rate or queue cap; `Retry-After: 60` |
| 503 | `application_unavailable` | Durable admission/read unavailable; `Retry-After: 30` |
| 500 | `internal_error` | Unexpected application failure, safely redacted |

Validation example: `{"repository_url":"http://127.0.0.1/private","branch":"main"}` with valid key returns 422:

```json
{"schema_version":1,"error":{"code":"validation_failed","message":"Request validation failed.","details":[{"field":"repository_url","code":"invalid_repository_url"},{"field":"branch","code":"unknown_field"}]}}
```

Allowed validation detail codes are `required`, `invalid_type`, `invalid_repository_url`, `invalid_idempotency_key`, `unknown_field`, `out_of_range`. Paths use request field/query/header names; never echo submitted values. Changed-body replay example (409):

```json
{"schema_version":1,"error":{"code":"idempotency_conflict","message":"Idempotency key is already bound to another request.","details":[]}}
```
