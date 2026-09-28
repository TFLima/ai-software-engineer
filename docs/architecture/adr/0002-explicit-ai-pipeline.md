# ADR 0002: Explicit AI pipeline

Status: Accepted (Phase 0 planning). Date: 2026-09-28.

## Context

The first workflow is known in advance. Autonomous planning and framework abstractions would make trust boundaries and failures harder to inspect.

## Decision

Use one `AnalysisOrchestrator` coordinating `RepositoryReader`, `FileSelector`, `ContextBuilder`, `LLMClient`, and `FindingValidator`. Use ordinary typed interfaces with injected adapters. The LLM produces candidate findings only; it cannot select tools or execute actions. Do not introduce LangChain, LangGraph, other agent frameworks, multiple agents, skills execution, or MCP in 0.1.

## Alternatives and consequences

A framework or multi-agent graph may eventually help richer workflows but introduces unnecessary execution semantics now. A single large prompt helper is simpler initially but mixes acquisition, budgeting, and validation. Explicit components allow independent tests and later adapters without a speculative plugin system. Specialized agents require new permission, budget, and coordination decisions in 0.5; they are not implied by naming an orchestrator.
