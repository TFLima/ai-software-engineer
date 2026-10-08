# B09 FindingValidator validation

B09 implements an independently callable `FindingValidator` in `services/ai/app/finding_validator.py`. It accepts candidate JSON, a trusted B07 `ContextResult`, frozen AI limits and an aware absolute deadline. It returns `ValidatedFindings` with the complete trimmed findings tuple and the original coverage; it performs no source/provider requests, execution, logging or persistence. The B10 orchestrator must retain the recorded SHA and provenance from acquisition/generation alongside this result. The internal endpoint still fails closed with `configuration_error` until B10.

## Enforced behavior

- Closed version-1 root, finding and evidence objects; exact types, enums, required fields and optional finite confidence. Duplicate JSON keys, non-finite constants, trailing content, Markdown fences and malformed/deep JSON fail as `invalid_findings`.
- All findings pass before any result is returned. Excess findings/evidence and oversized fields fail without truncation or salvage. Only contract-authorized text trimming occurs; Unicode code points determine text length. Control characters are rejected, allowing LF/TAB only in multiline fields.
- Evidence uses exact case-sensitive paths and original inclusive line numbers from B07 coverage. No Unicode/case normalization or percent decoding occurs. Paths must satisfy relative POSIX bounds; booleans/floating-point locations, duplicate evidence, absent paths and ranges crossing omitted lines fail. Adjacent included spans support a contiguous range without filling gaps.
- Empty findings require nonempty trusted inspected context and consistent positive coverage. Coverage counts and nonoverlapping spans are checked against limits. The evidence map is platform-owned input, never candidate-supplied data.
- Candidate UTF-8 bytes are bounded before JSON parsing. Validation stage and overall deadlines reserve cleanup time and are checked throughout processing. Oversized input/expired budgets produce `limit_exceeded`; malformed trusted inputs produce `invalid_request`, unsupported context policy produces `unsupported_schema`, and empty inspected context produces `no_eligible_context`. Invalid candidate schema versions produce `invalid_findings`.
- Advisory explanations/recommendations are preserved, with no invented confidence or semantic rewriting. Validation cannot establish truth, exploitability or advisory intent from arbitrary prose. Markup stays plain text and must be escaped by the later frontend.

## Verification

Run from the repository root after installing `services/ai/requirements-dev.txt`:

```sh
PYTHONPATH=services/ai python -m pytest services/ai/tests -q
python -m compileall -q services/ai/app services/ai/tests
git diff --check
```

Fixtures cover a real B07 context, valid/empty results, strict JSON and nested duplicate keys, whole-candidate rejection, text/count boundaries, confidence, unsafe/exact Unicode paths, duplicate/out-of-range evidence, omitted gaps, adjacent spans, forged coverage, deadline and response-byte caps, and plain-text markup. Full AI regression suite: **307 tests passed**. No paid provider call, live GitHub acquisition, Compose integration or backend persistence check was performed for B09. B10 owns orchestration, envelope assembly, independent Laravel validation and atomic persistence; B11 owns escaped display.
