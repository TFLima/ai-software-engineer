# ADR 0005: Structured findings with evidence

Status: Accepted (Phase 0 planning). Date: 2026-09-28.

## Context

LLM output can be malformed, unsupported by context, or unsafe to render. Free-form reports make validation and UI behavior unpredictable.

## Decision

Request a versioned JSON findings schema. `FindingValidator` enforces the [overview contract](../overview.md), including source paths and line ranges within the exact context from the resolved SHA. Reject the whole candidate if any finding is invalid. Laravel independently validates the envelope and atomically persists accepted findings with terminal state. Render plain text with escaping. Preserve model, prompt, policy, schema, and coverage provenance without saving source or prompts by default.

## Alternatives and consequences

Unstructured Markdown is easy to generate but hard to validate. Partial acceptance can obscure systematic failures and is deferred. Strict validation can reject otherwise useful responses; surface safe failures and test model contracts with fixtures. Structural and evidence checks do not establish semantic correctness. Findings remain advisory; an empty result does not certify safety.
