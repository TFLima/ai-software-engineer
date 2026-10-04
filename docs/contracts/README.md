# MVP 0.1 implementation contracts — v1

Status: B01 documentation deliverables complete; no runtime implementation. These contracts refine the accepted [overview](../architecture/overview.md) and [ADRs](../architecture/adr/README.md) without replacing their decisions.

| Contract | Implementation authority |
| --- | --- |
| [Lifecycle](analysis-lifecycle-v1.md) | Laravel state, attempts, retries and persistence |
| [Application API](application-api-v1.md) and [OpenAPI](application-api-v1.openapi.yaml) | Angular → Laravel submission, polling and pagination |
| [Internal API](internal-api-v1.md) and [OpenAPI](internal-api-v1.openapi.yaml) | Laravel worker → FastAPI synchronous run |
| [Findings](finding-schema-v1.md) | Provider-independent candidate validation and evidence |
| [Limits and access](limits-and-access-v1.md) | Central server defaults, deadlines and local boundary |

## Shared conventions

MUST and MUST NOT are requirements. JSON examples use synthetic UUIDs and SHA values. IDs are lowercase canonical UUID strings; commit SHAs are lowercase 40-character hexadecimal GitHub commit IDs. Timestamps are UTC RFC 3339 strings with `Z`. All JSON objects are closed: reject unknown fields at every nesting level, including requests, results, errors and findings. Required fields cannot be null unless explicitly allowed. JSON must reject duplicate keys, non-finite numbers and trailing content. Strings are Unicode; lengths below count Unicode code points unless bytes are specified. Text is plain text, escaped on display, with no executable markup interpretation. Reject NUL and control characters except LF and TAB in multiline text.

Public API contract version is `1` (response field `schema_version`); internal and finding versions are independently `1`. Request versioning for the public API is implicit in these MVP routes. Unsupported explicit versions are errors, never coerced. Additive fields also require a reviewed version change because readers reject unknown fields. No fallback, field dropping or schema repair is allowed. Implementation must publish matching OpenAPI definitions in later backlog items; this change supplies documentation only.

## B01 acceptance review

| B01 criterion | Evidence |
| --- | --- |
| Analysis lifecycle | Lifecycle transition tables, terminal rules, attempt identity, retry and reconciliation rules |
| Versioned finding schema with valid/invalid examples | Findings field table, evidence rules and candidate examples |
| Application request/result contracts with valid/invalid examples | Three application routes, idempotency, pagination and errors |
| Internal request/result contracts with valid/invalid examples | Internal envelopes, schema rejection, identity fence and authentication |
| Finite archive/file/context/token/concurrency/time/attempt limits | Central defaults table and strict timeout ordering |
| Loopback-only access scope | Single-operator scope and private-service boundary in limits/access |

Review outcome: criteria covered by documentation; runtime enforcement remains B02–B13. No architectural contradiction discovered. Provider/model and paid-call cost ceilings/data-use settings remain B08 gates; retention/deletion tuning remains B12. Numeric limits are conservative initial defaults, not measured optima.
