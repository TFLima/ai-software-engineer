# ADR 0004: Asynchronous lifecycle and durable storage

Status: Accepted (Phase 0 planning). Date: 2026-09-28.

## Context

Acquisition and model calls outlast normal browser requests and can fail or be delivered more than once.

## Decision

Laravel creates durable analysis rows in PostgreSQL and schedules jobs through Redis. A worker synchronously calls the internal AI endpoint within a bounded asynchronous job. PostgreSQL is the source of truth; Laravel alone writes analyses, attempts, and findings. Use submission idempotency, atomic attempt claims, bounded retries, timeout ordering, reconciliation, and transactional final persistence as described in the [overview](../overview.md). Stale results cannot replace active results. pgvector is available in the database platform but unused in 0.1.

## Alternatives and consequences

Browser-blocking analysis is fragile. Separate Python queues or callbacks introduce ownership and delivery complexity before there is measured need. Redis-only state is insufficient for durable result history. The chosen worker can remain occupied during AI processing and transport retries can repeat paid calls; concurrency and attempt budgets constrain costs. This is at-least-once work with idempotent persistence, not exactly-once execution.
