# ADR 0008: Explicitly configured OpenAI and Anthropic adapters

Status: Accepted for implementation by the explicit user request of 2026-10-18. Date: 2026-10-18.

## Context

The authorized multiprovider task extends MVP 0.1 beyond the one-real-provider
restriction in [ADR 0007](0007-llm-provider-abstraction.md). All other service,
trust and finding contracts remain unchanged.

## Decision

Supersedes ADR 0007's provider-count restriction. Preserve its platform-owned
`LLMClient` and `ModelAdapter`. One composition function selects OpenAI,
Anthropic or explicitly authorized development/test fake by environment. Missing
selection preserves OpenAI. Invalid configuration and provider failures never
trigger fallback. Anthropic Messages translates its own schema and usage and
requires separate operator policy acknowledgement. FindingValidator retains all
local validation.

Monetary ceilings remain $0.02/call and $0.04/attempt by default. Operators may
explicitly configure higher ceilings AND provider budgets as authorized by this
task, preserving integer accounting, token caps and bounded retries. See
[configuration and validation](../../development/multi-provider-llm-validation.md).

## Alternatives and consequences

The former single-provider restriction cannot meet the requested comparison.
Automatic routing/fallback and generic plugin frameworks remain excluded.
Models are finite reviewed profiles, not arbitrary identifiers. Provider
capabilities differ; local validation is mandatory. Paid calls, real latency
and finding quality remain pending separate authorization and execution.
