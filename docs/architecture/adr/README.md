# Architecture Decision Records

Accepted here means accepted for planning; it does not claim implementation. Date for all initial decisions: 2026-09-28. Supersede an ADR with a linked replacement when its decision changes.

| ADR | Decision |
| --- | --- |
| [0001](0001-service-boundaries.md) | Separate UI, application ownership, and AI processing |
| [0002](0002-explicit-ai-pipeline.md) | Use one explicit orchestrator without an agent framework |
| [0003](0003-untrusted-repository-snapshots.md) | Inspect bounded immutable snapshots without execution |
| [0004](0004-asynchronous-lifecycle-and-storage.md) | Laravel owns asynchronous lifecycle and durable results |
| [0005](0005-structured-findings.md) | Validate versioned findings and source evidence |
| [0006](0006-local-topology-and-evolution.md) | Start with Compose and defer advanced capabilities |
| [0007](0007-llm-provider-abstraction.md) | Keep provider details behind a platform-owned `LLMClient` interface |
