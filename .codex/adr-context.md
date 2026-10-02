# Discover project context for ADR tasks

This file defines how to obtain context; it does not record project status, selected stack, release scope or an inventory of accepted decisions. Resolve paths against the project root. These discovery rules take precedence over generic role examples and scoring heuristics.

## Read the sources of truth

1. Read `README.md` for the project overview and reported implementation status.
2. Read `docs/architecture/overview.md` and `docs/architecture/adr/README.md`; inspect relevant ADRs, including replacement links and status, to establish the selected stack, service ownership and accepted boundaries.
3. Read `docs/contracts/README.md` and the contracts relevant to the task for exact boundary rules and resource limits.
4. Read `docs/planning/mvp-0.1-backlog.md` and `docs/planning/roadmap.md` when determining release scope, deferred capabilities and acceptance gates. Treat these as planning documents, not proof of delivery.
5. Inspect the actual repository files for implementation evidence. If sources move, locate their replacements rather than assuming absence means the decision was revoked.

Derive the current stage, technologies and versions, service responsibilities, provider integration policy, runtime permissions, deployment scope and deferred work from these sources on every task. Do not maintain copies of that information in agent instructions. If sources conflict or are stale, cite the conflict and distinguish observed implementation from documented intent; do not silently choose a new architecture.

## Interpret evidence

Label planned decisions, accepted decisions, implemented behavior and deferred work separately. Documentary evidence can establish a planning decision without source code. Missing implementation is a defect only when the task scope or documented delivery commitments require it. A Git commit date is provenance, not automatically the decision or adoption date.

Technology examples and framework defaults in role instructions are illustrative, not evidence of adoption. Consult the current ADRs before proposing additional infrastructure or runtime capabilities. Preserve the product's documented provider abstraction; OpenAI model settings in `.codex/agents/*.toml` configure documentation tooling and do not choose the product's LLM provider.

## Discover ADR conventions

Formal ADRs default to `docs/architecture/adr`; analysis artifacts default to `docs/adrs`. Explicit task paths override defaults. Inventory actual formal decision files, excluding README/index documents, and inspect their naming, numbering, headings, section structure, language, status and date conventions. Continue the observed sequence; never hard-code the last ID, decision count, acceptance label or date.

Preserve existing metadata and decision content. New unaccepted decisions default to `Proposed`; acceptance or supersession requires evidence and an authorized decision update. Use evidenced dates and mark unknowns. Follow the established concise format instead of forcing generic seven-section MADR or minimum line counts. Logical module labels do not establish implemented directories. Check all relevant existing decisions for coverage before creating a new ADR.

## Evaluate relationships

Similarity and shared technology keywords identify candidates only. Require explicit replacement evidence for supersession and an architectural prerequisite for dependencies. Foundational decisions may be genuine prerequisites; do not exclude them solely because they are foundational. Preserve manual relationships and status. Validate/report-only tasks do not modify ADRs. Report conflicting links, missing targets and cycles instead of changing decision semantics automatically.
