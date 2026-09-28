# ADR 0001: Service boundaries

Status: Accepted (Phase 0 planning). Date: 2026-09-28.

## Context

The product needs an interactive UI, durable business workflows, and AI-specific processing with independent dependencies.

## Decision

Use Angular + TypeScript for the UI, Laravel 12 / PHP for the application API and queue worker, and Python + FastAPI for AI processing. Nginx serves the frontend and routes the application API. Laravel exclusively owns database access and lifecycle state. FastAPI is internal and returns typed envelopes; Angular accesses only Laravel.

## Alternatives and consequences

A single-language monolith would simplify operations but would not follow the selected stack or isolate AI dependencies. Browser-to-AI calls would bypass application policy and persistence. Three runtimes add deployment and contract maintenance costs; versioned APIs and fixture-based integration tests must keep them aligned. No additional services are justified for 0.1.
