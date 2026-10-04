# B07 ContextBuilder

B07 adds a separately callable `ContextBuilder.build(snapshot, selection,
limits, deadline, token_counter=None)` over B05's temporary snapshot and B06's
selection result. Call it before closing the snapshot context. The result holds
the rendered repository text, policy version `1`, measured context bytes/tokens
and exact coverage. No source text is logged or placed in a result envelope.

## Context policy v1

Process eligible files in sorted path order. Reopen each regular file without
following links, verify its manifest size and B06 text policy again, and render
complete original lines with a quoted relative path and 1-based line labels:

```text
FILE "src/app.py"
1: def run():
2:     pass
```

The builder includes a prefix of complete lines from each file. It stops that
file before exceeding `context_bytes` (including all path/line labels) or
`context_tokens`, then considers the next file. A file with no included line
counts as omitted with reason `context_budget`. Partially included files count
as included and receive a truncation limitation. Each included prefix becomes
one sorted, disjoint evidence span with original line numbers. The map is
created while rendering, subject to `context_files` and `context_spans`; it is
never trimmed afterward. Coverage includes inventory, eligible, included,
omitted and line counts, aggregated B06 omission reasons, and limitations.
Directory-only submodules are limitations without invented file counts.

When the configured model tokenizer is supplied, `token_counter` counts the
entire candidate rendered context for admission. Without one, the conservative
fallback treats each UTF-8 byte as a token. B08 owns the complete prompt,
provider tokenizer choice, input/output reservations and paid-call budgets.
If no line fits, the builder raises `no_eligible_context`; a corrupt or changed
snapshot fails safely. The stage honors `context_seconds` and reserves cleanup
time against the overall deadline. Repository instructions such as `AGENTS.md`
are rendered as untrusted source data; they never alter selection or budgets.

## Validation

| Check | Result |
| --- | --- |
| `python -m pytest -q -p no:cacheprovider` in `services/ai` | 171 passed, including B04–B06 regressions; one upstream AnyIO deprecation warning |
| `python -m compileall -q app tests` | Passed |
| `git diff --check` | Passed |

Fixtures cover deterministic ordering, original and blank lines, instruction
text as data, exact evidence spans and coverage totals, inclusive byte/token
boundaries, configured token counting, file/span caps, partial files, omissions,
changed source, symlinks, forged selection and deadline expiry. No live GitHub
request, provider call or B10 orchestration was run.
