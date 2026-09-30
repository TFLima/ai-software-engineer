# MVP 0.1 backlog

Status: planned; no items below are implemented by Phase 0. P0 items are required for MVP acceptance; P1 is optional follow-up. IDs define dependencies rather than calendar estimates. The [overview](../architecture/overview.md) is the contract source and the [ADRs](../architecture/adr/README.md) record decisions.

B01 documentation deliverables are complete in the [versioned implementation contracts](../contracts/README.md), including the acceptance comparison. Other items remain planned; no application/runtime implementation is claimed.

| ID | Priority | Work item | Dependencies | Acceptance criteria |
| --- | --- | --- | --- | --- |
| B01 | P0 | Define minimum implementation contracts and policies | None | Specify analysis lifecycle and versioned findings schema, application API and internal request/result contracts with valid/invalid examples; set initial conservative finite archive/file/context/token/concurrency/time and attempt limits; agree loopback-only access scope |
| B02 | P0 | Bootstrap selected services and Compose topology | B01 | Angular/TypeScript, Laravel 12/PHP API and worker, FastAPI, PostgreSQL/pgvector, Redis and Nginx start with documented commands and health checks; only loopback Nginx exposed; secrets absent from Git; vector functionality unused |
| B03 | P0 | Implement relational lifecycle and API | B02 | Migrations store analyses/attempts/findings and provenance; submit returns 202; duplicate key returns same analysis and changed body conflicts; invalid URL rejected; status and paginated findings match contracts; no results presented as ready before completion |
| B04 | P0 | Implement reliable queue handoff | B03 | Job claims one active attempt; worker authenticates to internal FastAPI; timeout ordering and attempt caps enforced; missing queue publication and expired attempts reconciled; duplicate/stale results cannot overwrite state; transient retries and terminal errors tested |
| B05 | P0 | Implement `RepositoryReader` | B01, B02 | Public GitHub URL resolves to SHA and bounded snapshot; redirect/address SSRF controls, safe extraction and resource limits tested; unsafe links/paths rejected; submodules/LFS skipped and reported; no repository commands executed; temporary data cleaned on failure and success; establish GitHub quota handling and refine request pacing from observed responses within the initial limits |
| B06 | P0 | Implement `FileSelector` | B05 | Deterministically identify structure and select eligible text; binary/generated/vendor/sensitive paths filtered; limits enforced; fixture manifests verify selection and exclusion reasons |
| B07 | P0 | Implement `ContextBuilder` | B06 | Preserve paths and original line numbers, deterministic order, versioned policy and bounded token budget; report inspected/omitted context; repository instruction fixtures remain data; no embeddings or retrieval required |
| B08 | P0 | Implement `LLMClient` | B01, B07 | Platform-owned `LLMClient` interface with one real provider adapter and a fake adapter follows [ADR 0007](../architecture/adr/0007-llm-provider-abstraction.md); choose provider/model and data-use/retention settings before sending source; configure bounded cost budgets before paid calls and refine budgets, timeouts and retries from measurements; support provider-independent structured output and usage metadata; no tool calls; source/prompt/secrets excluded from logs; provider disclosure documented |
| B09 | P0 | Implement `FindingValidator` | B01, B07 | Reject invalid JSON, unknown fields, unsupported enums, excessive fields/counts, and out-of-context evidence; reject whole invalid candidate; accept valid empty findings with coverage; preserve advisory wording |
| B10 | P0 | Integrate `AnalysisOrchestrator` and persistence | B04, B05, B06, B07, B08, B09 | Execute fixed stages with correlation/deadline checks and cleanup; Laravel revalidates envelope; findings and completed status commit atomically; failure envelopes preserve known provenance; crash/duplicate fixtures cannot create partial or duplicate results |
| B11 | P0 | Implement frontend analysis flow | B03, B10 | User submits public URL, sees queued/running/completed/failed, polls with bounded backoff, and views paginated findings with SHA/line evidence and coverage; output escaped; errors actionable without leaking internals; disclose source transmission before submission |
| B12 | P0 | Establish baseline operations and data lifecycle | B10 | Safe stage timings, queue age, error codes, usage and cleanup failures visible by analysis/attempt ID; establish local result retention/deletion defaults and tune them using implementation evidence; configured deletion removes results and stale workspaces; document startup, failure recovery and operator retry; logs exclude raw source/prompts/provider output |
| B13 | P0 | Verify integrated MVP | B11, B12 | Demonstrate full eight-step product flow on a small public repository pinned in test evidence; lightweight evaluation uses deterministic fixtures, fake LLM responses, schema/evidence validation and basic regression tests for representative success/failure cases; malformed responses, unavailable provider, missing/private repo, oversize archives, unsafe paths, prompt injection text, queue loss, stale attempts and XSS payloads handled as specified; manually assess finding usefulness and record limitations |
| B14 | P1 | Refine result navigation | B13 | Add category/severity filtering and source navigation without changing core contracts or expanding source access |

## Implementation sequence

First settle minimum contracts and initial conservative limits (B01), then establish local infrastructure and lifecycle (B02–B04). Build bounded acquisition and context (B05–B07), provider and validation adapters (B08–B09), and integrate the pipeline (B10). Finish the user flow, operational controls, and acceptance demonstration (B11–B13). GitHub quota handling is refined in B05, provider operations and detailed cost budgets in B08, and local retention/deletion tuning in B12; these do not block starting implementation. Initial finite limits remain enforced, and provider data handling and bounded cost budgets must be set before real-provider calls. Independent components may be developed separately against agreed fixtures, but no service should bypass these integration gates.

## MVP acceptance and exclusions

Every P0 item must pass its acceptance criteria. The eight user-visible steps are covered by B11 (URL submission), B03–B04 (registration), B05 (read-only acquisition), B06 (structure/files), B07 (context), B08/B10 (structured generation), B09/B10 (validation and persistence), and B11 (display).

Basic evaluation starts in MVP 0.1 with deterministic fixtures, fake LLM responses, schema and evidence validation, basic regression tests, and representative success/failure cases (B06–B10, B13). Verification must cover success and failure paths, strict contracts, resource boundaries, persistence idempotency, and evidence provenance. Security checks must verify enforced behavior, not merely assert that a prompt contains protective wording. Real-provider runs use explicit bounded budgets; reproducible automated tests use fixtures and a fake provider.

No private repository credentials, repository writes, code execution, automatic fixes, embeddings/RAG, autonomous tools, specialized skills/agents, agent framework, MCP integration, production public deployment, or advanced evaluation platform are included. See the [roadmap](roadmap.md) for later capability decisions.

## Phase 0 review checklist

- README accurately says documentation only; no runtime implementation is claimed.
- Stack, ownership, lifecycle, result contract, and trust boundaries agree across overview and ADRs.
- Every step of the requested MVP flow maps to backlog acceptance criteria.
- Incremental releases 0.1–0.7 are documented without making later components 0.1 dependencies.
- Blocking implementation choices and verification requirements are visible before implementation starts.
