# B05 RepositoryReader

B05 builds on published B04 commit `1410b34` on `feat/mvp-0.1-b05`.
It implements a separately callable acquisition component. B06–B10 still own
selection, context, provider calls, finding validation and pipeline integration.
The HTTP run endpoint continues to fail closed with `configuration_error`.

## Component contract

`RepositoryReader.snapshot(repository, commit_sha, limits, deadline)` is an async
context manager. Inputs are canonical `{owner,name,url}`, nullable lowercase
40-character SHA, frozen AI limits, and an aware absolute UTC deadline. Consume
the snapshot inside the context; its paths become invalid when the context exits.
Reuse one reader in B10 so process-local quota cooldowns survive invocations.

Immutable `Snapshot` contains a temporary root, resolved SHA, sorted
`ManifestEntry(path,size,omission)` records, submodule paths and safe limitations.
Counts/sizes include regular files later omitted as LFS/submodules. Directory-only
submodules produce limitations rather than invented file counts. Empty trees are
valid acquisitions; B06 decides whether eligible context exists. Paths use NFC
normalization and colliding aliases are rejected.

`AcquisitionError` carries only a lifecycle code, retryability and known SHA.
Missing/private/renamed identities fail `repository_unavailable`; supplied SHAs
never fall back to a new branch head. Duplicate-key/malformed metadata fails
safely. No raw upstream body, source, credential or exception message is logged.

## Network and quotas

Construct fixed public metadata/default-head endpoints on `api.github.com` and a
SHA tar.gz endpoint on `codeload.github.com`. Check public visibility and matching
identity first. Resolve head once; archive retries retain the SHA. No checkout,
repository command, credentials, LFS/submodule URL or source endpoint is used.
Instruction files remain data.

Each physical GET validates all DNS addresses and connects to the validated
numeric IP; TLS certificate verification, SNI and HTTP Host use the original
hostname. Mixed private/public answers, private/reserved/loopback/link-local/
multicast and IPv6 transition addresses are blocked. There is no second hostname
resolution, ambient proxy, cookies, authorization, automatic redirect or HTTP
decompression. Every redirect revalidates exact HTTPS hosts and rejects
credentials, custom ports, queries, fragments and control characters.

Redirects and retries count against eight physical requests per attempt.
Connect/TLS and entire logical request deadlines include DNS, headers and streamed
body, without extending on activity. Headers/trailers have an additional 32 KiB
cap and informational responses a four-response cap. Every response body,
including errors, redirects and partial failed downloads, counts toward transfer
limits. Content-Length never admits a body alone; retries truncate partial files.

HTTP 429, exhausted-quota/Retry-After HTTP 403, and recognized secondary-limit 403
JSON messages map to `upstream_rate_limited`. Other forbidden/inaccessible
responses are terminal repository failures. Observe Retry-After seconds/date and
X-RateLimit-Reset with a one-second boundary margin. Missing usable rate-limit
timing implies at least 60 seconds. Successful exhausted responses also set a
next-request cooldown without discarding their metadata/SHA. API/codeload
cooldowns are separate. A wait that cannot fit acquisition time fails immediately.
Cooldowns are process-local and lost on restart; fleet coordination is outside
this single-service MVP.

Transient network/5xx failures allow two logical operation tries. Backoff starts
at the configured one second, increases with try index and respects larger quota
waits. All waits/requests stay within frozen stage, transfer and request budgets,
reserving cleanup time. The policy follows GitHub's
[rate-limit guidance](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).
Tests exercise synthetic observed response headers; no live throughput/quota
measurements or optimal-pacing claim is made.

## Extraction and cleanup

Parse tar.gz and PAX/GNU path records explicitly; never invoke archive extraction
helpers. Count physical headers including extension records. Accept one wrapper,
regular files and directories. Reject absolute/traversal/control/backslash/
drive-like paths, normalized duplicates, file/directory collisions, symlinks,
hardlinks, devices, FIFOs, sparse files and unsupported extension overrides.
Ignore archive owners/times/execute permissions. Workspaces/direct roots are
0700; regular files and archives are 0600.

All regular bytes, including excluded files, obey per-file and expanded-byte
ceilings. Extension metadata has additional 8 KiB per-record and 64 KiB aggregate
bounds. Whole inflation is capped at regular-byte allowance plus
`archive_entries * 1024 + 65536` header/padding/metadata allowance; zero-padding
bombs are bounded too. Check monotonic acquisition time during streaming and
validate gzip trailer, tar termination and absence of nonzero trailing payload.

Parse `.gitmodules` only as inert text without interpolation; never fetch its
URLs. Omit any regular entries beneath declared submodule paths. Invalid
configuration yields a safe fixed limitation. LFS pointers are inventoried and
removed without fetching objects. B06 owns binary/vendor/generated/sensitive
selection.

Context exit cleans on success, acquisition failure and cancellation. Removal
runs outside the event loop with the configured cleanup wait ceiling. If deletion
blocks, its already-started thread may finish later. Failures log only
`snapshot_cleanup_failed`, preserving the primary result/error. Scheduled stale
cleanup remains B12 work. Snapshots are not stored in PostgreSQL, returned by HTTP
or sent to a model.

## Validation

| Check | Result |
| --- | --- |
| `python -m pytest -q -p no:cacheprovider` in `services/ai` | 130 tests passed, including 33 existing B04 tests; one dependency deprecation warning |
| Python compilation | Passed |
| Git whitespace/diff and base checks | Passed; base is published B04 `1410b34` |

Fixtures cover SHA pinning, branch escaping, unavailable/private metadata,
resource limits and exact boundaries, malicious/corrupt tar/gzip, PAX/GNU forms,
metadata/padding bombs, DNS address validation and pinning, TLS verification
settings, headers/slow streams, redirects, partial download retries, aggregate
bytes, quota cooldowns, empty trees, LFS/submodules, inert instructions, expiry
and cleanup errors.

Tests exercise the production parser/transport with injected DNS/connect streams
and deterministic in-memory metadata/archive fixtures. No live GitHub acquisition,
external TLS handshake, source execution or provider call was performed. Docker
is absent; full Compose rebuild, container health/browser checks were not run.
Python 3.12 installed declared requirements including pinned `h11==0.16.0`,
previously a transitive Uvicorn dependency. No migration or Laravel change is
required.
