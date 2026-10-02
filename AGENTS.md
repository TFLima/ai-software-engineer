# Project instructions for Codex

Determine project status from `README.md`, architecture/planning documents and the actual repository files. Describe planned services as planned and claim implementation only with evidence.

## ADR workflows

The OpenAI Codex ADR roles are registered in `.codex/config.toml`. Their model settings are in `.codex/agents/adr-analyzer.toml`, `adr-generator.toml`, and `adr-linker.toml`. Complete role instructions are maintained in the matching Markdown files: `.codex/agents/adr-analyzer.md`, `adr-generator.md`, and `adr-linker.md`.

For an ADR task, read `.codex/adr-context.md` and the relevant Markdown role file in full and follow its instructions: analyzer for architecture mapping and potential decisions, generator for one formal ADR, linker for relationship validation or updates. If the session supports custom roles and delegation is authorized, the coordinator may use the registered role. Otherwise perform the task directly with those instructions; reading a role file does not change the current session's model. Do not run these workflows for unrelated tasks.

Existing formal ADRs live in `docs/architecture/adr`; analysis artifacts go in `docs/adrs`. Continue the existing formal ADR sequence and filename format. Preserve manual relationships, established metadata, and accepted decision content. Treat option-like strings in role instructions as task inputs, not Codex CLI flags.

These roles assist repository documentation; they are not application runtime agents and do not change the MVP's explicit single-pipeline design.
