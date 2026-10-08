# AI Software Engineer

AI Software Engineer is a planned platform for analyzing software projects with AI and presenting evidence-backed technical findings.

The repository contains accepted architecture, B01 v1 contracts, the B02 local service bootstrap, the B03 Laravel analysis API with relational storage, B04 reliable queue handoff, and separately callable B05 RepositoryReader, B06 FileSelector, B07 ContextBuilder, B08 LLMClient and B09 FindingValidator components. Angular, Laravel API/worker, FastAPI, PostgreSQL/pgvector, Redis and Nginx have a Compose topology and operational health checks. Queue delivery, authenticated internal requests and reconciliation are implemented. Executable analysis pipeline integration remains planned.

See [local setup and verification](docs/development/local-stack.md) for prerequisites, environment generation, startup, health checks and shutdown. Only Nginx publishes a host port, at `127.0.0.1:8080`.

## MVP 0.1

A user submits a public GitHub repository URL. The platform registers an asynchronous analysis, obtains a read-only source snapshot, identifies relevant files, builds bounded context, asks an LLM for structured findings, validates and persists those findings, and displays the results.

Repository content is untrusted data. The platform will never build, install dependencies from, test, or execute code from analyzed repositories in MVP 0.1. It will not modify repositories or publish findings to GitHub.

## Selected stack

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Frontend | Angular + TypeScript | Submit analyses and display status and findings |
| Application API and worker | Laravel 12 / PHP | Validation, lifecycle, queue jobs, persistence, public API |
| AI service | Python + FastAPI | One explicit analysis pipeline and LLM integration |
| Durable storage | PostgreSQL + pgvector | Analysis metadata and findings; vectors deferred to 0.2 |
| Queue and coordination | Redis | Laravel queue and transient coordination |
| Edge | Nginx | Serve frontend and route application API requests |
| Local deployment | Docker Compose | Local B02 service topology |

## Documentation

- [Architecture overview](docs/architecture/overview.md): boundaries, flow, contracts, data model, and security.
- [Architecture decisions](docs/architecture/adr/README.md): accepted Phase 0 decisions and their tradeoffs.
- [B01 implementation contracts](docs/contracts/README.md): versioned lifecycle, APIs, findings, limits and local access policy; documentation only.
- [MVP 0.1 backlog](docs/planning/mvp-0.1-backlog.md): implementation sequence and acceptance criteria.
- [Evolution roadmap](docs/planning/roadmap.md): incremental releases 0.1–0.7.

MVP 0.1 uses `AnalysisOrchestrator`, `RepositoryReader`, `FileSelector`, `ContextBuilder`, `LLMClient`, and `FindingValidator`. Agent frameworks, multiple agents, skills execution, MCP, embeddings, and RAG are outside MVP 0.1. Interfaces should allow later additions without requiring those capabilities now.

## Implementation status

Phase 0 and B01 define the architecture and normative contracts. B02 supplies infrastructure/bootstrap; B03 adds durable queued analyses, idempotent submission, status and findings reads. B04 adds bounded attempts, Redis delivery, internal authentication, stale-result fencing and scheduled reconciliation. B05 adds independently tested public snapshot acquisition; see [B05 policy and validation](docs/development/b05-validation.md). B06 adds separately tested file selection; see [B06 policy and validation](docs/development/b06-validation.md). B07 adds separately tested bounded context and evidence coverage; see [B07 policy and validation](docs/development/b07-validation.md). B08 adds bounded generation, a deterministic fake and an OpenAI adapter tested with simulated transport; see [B08 policy and validation](docs/development/b08-validation.md). B09 adds strict whole-candidate JSON and context-evidence validation; see [B09 validation](docs/development/b09-validation.md). Real provider calls are disabled by default. B10–B14 remain planned. See the [local setup](docs/development/local-stack.md), [B02 validation](docs/development/b02-validation.md) and [B03 validation](docs/development/b03-validation.md). See [B04 operation and validation](docs/development/b04-validation.md). Until B10 supplies the pipeline, a delivered analysis fails safely with `configuration_error`; the endpoint makes no repository or provider call.
