# ADR 0006: Local topology and incremental evolution

Status: Accepted (Phase 0 planning). Date: 2026-09-28.

## Context

The project needs a reproducible integration target while its analysis workflow is still being established.

## Decision

Plan Docker Compose for the selected services with Nginx as the only public entry point, initially bound to loopback for one operator. Internal services and runtime secrets stay private. Production hosting and public access require a separate authentication/authorization decision. Introduce capabilities in the [roadmap](../../planning/roadmap.md) order: orchestrator, RAG, tools, skills, agents, MCP, then advanced evaluation/observability. Baseline testing, logging, and resource controls start in 0.1.

## Alternatives and consequences

Kubernetes and a generalized agent platform would increase operational work without a demonstrated 0.1 requirement. Compose simplifies local integration but is not a production readiness claim. Interfaces provide future extension seams; no inactive implementations or vector infrastructure beyond the chosen database capability should be built early. Later releases require evidence and focused ADRs before changing trust boundaries.
