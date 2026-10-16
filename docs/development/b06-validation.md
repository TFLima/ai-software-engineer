# B06 FileSelector

B06 adds a separately callable `FileSelector.select(snapshot, limits, deadline)`
over B05's immutable manifest and temporary snapshot root. It returns versioned
selection decisions, eligible file metadata, sorted implied directories and
omission counts. It does not return source bytes, execute repository content or
call a provider. Call it while the B05 snapshot context remains open. B07
builds bounded context from eligible files; `context_files`, context bytes and
token budgets are not spent by B06.

## Selection policy v1

Process every regular manifest entry in path order. Preserve B05 `lfs` and
`submodule` omissions without opening those files. Then apply path rules in this
order: sensitive paths, vendored dependency trees, generated/build outputs,
known binary extensions and unsupported file types. For remaining candidates,
read at most the manifest's bounded file size and require UTF-8 text without
NUL/other control characters. Exclude recognized private-key/token patterns and
generated headers. Empty files are `unsupported_text`. Source files, common
configuration formats, documentation and instruction files such as `AGENTS.md`
are eligible data; their contents never control selection policy.

Path rules include `.env` variants, credentials/secret files, private-key
formats, Terraform state/variables, dependency directories such as
`node_modules`/`vendor`, build directories such as `dist`/`coverage`, lockfiles,
minified assets and maps. The exact v1 sets and patterns live in
`services/ai/app/file_selector.py`. The content scanner uses high-confidence
token/private-key signatures; it cannot guarantee detection of every secret.
No source text, token or path is logged by the selector.

The selector verifies manifest path normalization/uniqueness, file count, file
and aggregate sizes, regular-file type and exact bytes read. It opens each path
component without following symlinks, then closes all descriptors. The
`select_seconds` budget and remaining overall deadline reserve cleanup time.
Corrupt snapshots fail safely. It inventories all eligible files up to B05's
`file_count`; the B07 ContextBuilder decides which fit `context_files` and
context budgets.
Implied directories come from file paths; B05 does not inventory empty dirs.

## Validation

| Check | Result |
| --- | --- |
| `python -m pytest -q -p no:cacheprovider` in `services/ai` | 158 passed, including B04/B05 regression tests; one upstream AnyIO deprecation warning |
| `python -m compileall -q app tests` | Passed |
| `git diff --check` | Passed |

Fixture manifests cover deterministic order, inventory/directory counts,
eligible text, LFS/submodule carry-through, binary/generated/vendor/sensitive
and unsupported reasons, content signatures, inclusive file limits, malformed
manifests, symlink/size mismatch, deadline expiry and empty selection. No live
GitHub request, source execution, provider call or B10 orchestration was run.
