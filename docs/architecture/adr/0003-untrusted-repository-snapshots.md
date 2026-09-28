# ADR 0003: Bounded read-only source snapshots

Status: Accepted (Phase 0 planning). Date: 2026-09-28.

## Context

Public repositories can contain malicious archives, instructions, secrets, oversized data, and executable configuration. Analysis needs reproducible evidence without trusting repository authors.

## Decision

Accept canonical public GitHub repository identities only. Resolve an immutable commit SHA and retrieve a bounded snapshot using fixed allowlisted endpoints. Extract defensively into an isolated temporary workspace, reject unsafe entries, and inspect text only. Never execute repository code, hooks, dependency installation, builds, tests, or configuration-driven tools. Do not follow submodules, LFS references, or source-provided URLs. Apply finite limits and cleanup, preserve provenance, and treat repository instructions as untrusted data.

## Alternatives and consequences

A general URL fetcher expands SSRF exposure. A full checkout with recursive dependencies adds surface area without improving the initial text analysis enough to justify it. Sandboxed code execution still creates a separate security problem and is excluded. Static inspection misses runtime behavior and omitted dependencies; results must disclose coverage. Future tools require individual trust reviews; the roadmap does not authorize code execution.
