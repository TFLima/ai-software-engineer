# ADR 0007: Platform-owned LLM provider interface

Status: Accepted (Phase 0 planning). Date: 2026-09-28.

## Context

The platform may later evaluate other hosted or local models. Coupling orchestration or finding contracts to one provider SDK would make those comparisons harder and would complicate deterministic tests. MVP 0.1 needs only one real provider integration.

## Decision

The AI pipeline depends on a platform-owned `LLMClient` interface. `AnalysisOrchestrator` and other core components must not depend directly on a provider SDK. Keep provider-specific request construction, response translation, errors, and usage details behind the adapter, returning the platform's candidate JSON and usage metadata. The core finding contract remains provider-independent, and `FindingValidator` remains responsible for validating candidates and evidence.

For MVP 0.1, implement one real provider adapter and a fake adapter for deterministic tests. Define only the interface needed by the current pipeline; do not build a generic provider framework, plugin system, dynamic provider registry, or multi-provider routing. Later hosted or local model adapters can be evaluated against the same contracts and fixtures when needed.

## Alternatives and consequences

Direct SDK calls from the orchestrator would reduce initial adapter code but spread provider assumptions through the pipeline and its tests. A generic provider framework would add speculative complexity. The narrow interface isolates provider details and supports repeatable tests at a small translation cost. It does not imply equivalent model capabilities or quality: any future adapter must demonstrate compatibility with the finding contract and be evaluated before adoption.
