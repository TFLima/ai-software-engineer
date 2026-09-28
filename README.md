# AI Software Engineer

AI Software Engineer is a planned platform for analyzing software projects with AI and presenting evidence-backed technical findings.

The repository currently contains **Phase 0: architecture and planning only**. No application services, containers, migrations, or executable analysis pipeline are implemented. There are no setup or run commands yet.

## MVP 0.1

A user submits a public GitHub repository URL. The platform registers an asynchronous analysis, obtains a read-only source snapshot, identifies relevant files, builds bounded context, asks an LLM for structured findings, validates and persists those findings, and displays the results.

Repository content is untrusted data. The platform will never build, install dependencies from, test, or execute code from analyzed repositories in MVP 0.1. It will not modify repositories or publish findings to GitHub.

## Planned stack

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Frontend | Angular + TypeScript | Submit analyses and display status and findings |
| Application API and worker | Laravel 12 / PHP | Validation, lifecycle, queue jobs, persistence, public API |
| AI service | Python + FastAPI | One explicit analysis pipeline and LLM integration |
| Durable storage | PostgreSQL + pgvector | Analysis metadata and findings; vectors deferred to 0.2 |
| Queue and coordination | Redis | Laravel queue and transient coordination |
| Edge | Nginx | Serve frontend and route application API requests |
| Local deployment | Docker Compose | Reproducible service topology, to be implemented later |

## Documentation

- [Architecture overview](docs/architecture/overview.md): boundaries, flow, contracts, data model, and security.
- [Architecture decisions](docs/architecture/adr/README.md): accepted Phase 0 decisions and their tradeoffs.
- [MVP 0.1 backlog](docs/planning/mvp-0.1-backlog.md): implementation sequence and acceptance criteria.
- [Evolution roadmap](docs/planning/roadmap.md): incremental releases 0.1–0.7.

MVP 0.1 uses `AnalysisOrchestrator`, `RepositoryReader`, `FileSelector`, `ContextBuilder`, `LLMClient`, and `FindingValidator`. Agent frameworks, multiple agents, skills execution, MCP, embeddings, and RAG are outside MVP 0.1. Interfaces should allow later additions without requiring those capabilities now.

## Phase 0 completion

Phase 0 defines the architecture, records its main decisions, and supplies an actionable backlog. Runtime implementation and verification belong to subsequent work. Documentation review establishes design consistency, not proof of runtime security or model accuracy.
