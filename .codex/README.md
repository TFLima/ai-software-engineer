# ADR agents for OpenAI Codex

The three roles were adapted from [devfullcycle/claude-mkt-place](https://github.com/devfullcycle/claude-mkt-place/tree/main/plugins/adrs-management/agents). The original Claude YAML front matter and Task-tool examples have been replaced with native Codex TOML role configuration and separate Markdown instructions.

| Role | Model | Reasoning | Purpose |
| --- | --- | --- | --- |
| adr-analyzer | gpt-6.1 | high | Map architecture and identify potential ADRs |
| adr-generator | gpt-6.1 | medium | Generate one formal ADR from one potential decision |
| adr-linker | gpt-6.1 | high | Validate or update ADR relationships |

`config.toml` registers role-specific config files. Each TOML role file contains model settings and a short `developer_instructions` directive that tells the agent to read its matching `.md` file. The Markdown file is the single source of truth for role instructions; edit it for workflow changes and edit the TOML for model settings. Codex loads the TOML configuration; the agent reads the Markdown through its file-reading tools before working. This preserves Codex's built-in model instructions without assuming a native Markdown include setting. Project configuration must be trusted/loaded by the client. Custom-role and delegation availability depends on the Codex version and session settings; no global configuration or authentication is changed here.

The model string is a requested model, not proof of account access. Model availability has not been verified through a live inference call. If `gpt-6.1` is unavailable, select an OpenAI model offered by your Codex client and update `model` in each role file. The suggestions from the earlier conversation are not a verified public API model catalog. These files configure Codex; they are not a standalone Responses API implementation.

## Usage

Start a new Codex session at the repository root after trusting the project configuration. Request the role and task in the prompt, for example:

- “Use adr-analyzer to map this project. Put analysis artifacts in docs/adrs and inspect existing ADRs in docs/architecture/adr.”
- “Use adr-generator to turn docs/adrs/potential-adrs/must-document/API/example.md into one formal ADR in docs/architecture/adr.”
- “Use adr-linker to validate relationships in docs/architecture/adr without changing files.”

These are prompts, not installed slash commands. `--project-dir`, `--adrs-dir`, `--output-dir`, `--language`, `--validate`, and `--report-only` appearing in instructions describe task inputs; do not pass them as top-level Codex CLI arguments. Natural-language equivalents are accepted.

If custom-role delegation is unavailable, root `AGENTS.md` tells Codex to read and apply the selected role instructions directly. In that mode the current session retains its selected model; choose the desired model and reasoning effort in the client. Multiple ADRs are generated serially unless a coordinator can reserve unique numbers and output paths and serialize index updates.

## Stack and scope alignment

All three roles first read `adr-context.md`, a discovery guide that points to project sources of truth. Stack, project stage, ownership, release scope and ADR inventory are read from those sources on each task, rather than duplicated in agent instructions. The Codex model settings do not choose the product LLM provider.

The generator follows the existing three-section ADR format and defaults new decisions to Proposed. The analyzer checks existing decision coverage before suggesting new ADRs; the linker requires decision evidence, preserves manual metadata and reports conflicts without automatically changing acceptance.

## Project conventions

Formal ADRs use the existing `docs/architecture/adr/0001-title.md` convention. Mapping, potential decisions, indexes and reports use `docs/adrs`. Explicit task paths override defaults. Existing metadata and decision content take precedence over generic MADR examples. Evidence from documentation must be labeled as planned when there is no implementation. Unknown dates and rationale are marked rather than invented.

Source provenance (Git blob SHA before adaptation): analyzer `2ebb824463ddb68843cda27b4a47cd2e5bd4196d`, generator `0dce909412c70d118d5d229f411c61ceb822e3a7`, linker `1ac307e703881780c26aa48f51213436801370eb`.
