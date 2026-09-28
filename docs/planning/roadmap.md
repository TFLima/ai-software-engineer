# Planned evolution

These releases are a sequence of capabilities, not delivery dates. Each builds on the preceding release and requires its own scoped design review. The no-execution and untrusted-input policies remain in force unless explicitly superseded by a reviewed decision.

| Release | Capability | Entry point and completion evidence |
| --- | --- | --- |
| MVP 0.1 | Single analysis orchestrator | Complete the [backlog](mvp-0.1-backlog.md); demonstrate public URL → persisted, evidenced findings in the UI with failure handling; begin lightweight evaluation with deterministic fixtures, fake LLM responses, schema/evidence validation, basic regression tests and representative success/failure cases |
| 0.2 | Embeddings and RAG | Experiment with embeddings/retrieval in `ContextBuilder`; design chunking, embedding versioning, pgvector schema/indexes, repository/SHA isolation, invalidation and deletion; evaluate against the deterministic MVP 0.1 `FileSelector` + `ContextBuilder` baseline on comparable fixtures and model settings, measuring finding quality, evidence retrieval/coverage, token usage, latency and cost; adopt RAG only if the comparison demonstrates benefit, not merely because it is available |
| 0.3 | Richer analysis tools | Add explicit bounded static-analysis adapters coordinated by the orchestrator; document each tool's input/output, permissions and provenance; no repository code execution |
| 0.4 | Specialized skills | Introduce versioned reusable analysis instructions/policies for particular tasks; trusted platform-owned skills remain distinct from repository text; compare results against baseline fixtures |
| 0.5 | Specialized agents | Introduce scoped roles only for demonstrated workflow benefits; define coordination, independent budgets, shared evidence, permissions and failure semantics before adoption of any agent framework |
| 0.6 | MCP | Add reviewed protocol adapters for selected tools/resources; define authentication, authorization, transport boundaries, allowlists, auditability and user approval rules for any side effects |
| 0.7 | Advanced evaluation and observability | Expand 0.1 evaluation into larger benchmark datasets, systematic quality/regression gates, cost and latency analysis, distributed tracing with redaction, and more mature evaluation infrastructure; validate improvements across earlier capabilities |

The architecture does not require a framework in any release. Adopt one only if a later ADR shows a concrete benefit over explicit components. Basic evaluation, security tests, structured logs, usage tracking, and correlation IDs are 0.1 obligations; 0.7 expands their depth and coverage.
