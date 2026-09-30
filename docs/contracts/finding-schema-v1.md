# Finding schema — v1

Candidate root is exactly `{ "schema_version": 1, "findings": [...] }`. Findings have no model-generated IDs. The internal envelope carries this array and `finding_schema_version: 1`; Laravel adds public IDs after persistence. Validate the entire candidate before accepting any item. See [limits](limits-and-access-v1.md) and [shared JSON rules](README.md).

| Field | Required | Constraint |
| --- | --- | --- |
| `category` | Yes | `architecture`, `maintainability`, `reliability`, `security`, `testing` |
| `severity` | Yes | `info`, `low`, `medium`, `high`, `critical` |
| `title` | Yes | Plain text, 1–160 characters after trimming; no LF/TAB |
| `explanation` | Yes | Plain text, 1–4000 characters after trimming |
| `recommendation` | Yes | Plain text, 1–2000 characters after trimming; advisory action |
| `evidence` | Yes | Array of 1–5 closed evidence objects; no identical entries |
| `confidence` | No | Finite JSON number from 0 through 1 inclusive; null forbidden |

Severity denotes potential impact: `info` observation, `low` localized minor concern, `medium` meaningful bounded impact, `high` substantial reliability/security/design impact, `critical` potentially severe compromise or outage. These are advisory model assessments, not a verified exploit claim. Confidence is optional model self-assessment, not calibrated probability or ranking guarantee; omission means unavailable, not zero. Never invent confidence in the adapter.

Each evidence object has exactly `path`, `start_line`, `end_line`. Path is a case-sensitive relative POSIX path after stripping the archive's single repository wrapper; 1–512 characters, at most 12 nonempty segments; no leading/trailing slash, backslash, drive prefix, NUL/control characters, `.` or `..` segments. Do not decode percent escapes or rewrite Unicode/case when matching the manifest. Lines are JSON integers (booleans forbidden), 1-based, inclusive, with `1 <= start_line <= end_line`. Every line in the range must exist in the exact selected context for the recorded SHA, including when a file has disjoint included spans. A path present only in the archive or selected inventory is insufficient. Evidence cannot cross omitted spans or use renumbered snippet lines.

Both services validate structure; FastAPI validates against ContextBuilder's exact evidence map. Laravel revalidates evidence against the bounded `coverage.included_spans` in the authenticated envelope, without source storage or database access by FastAPI. This trusts the internal service's context construction, not the model's asserted locations. If any item is invalid or findings exceed 20, reject the whole candidate as `invalid_findings`; do not truncate or salvage. An empty array is valid only with genuine nonempty inspected context and coverage, and does not certify repository quality.

## Valid candidate

Fixture premise: `app/Services/ReportService.php` lines 10–18 were included verbatim from the resolved SHA.

```json
{
  "schema_version": 1,
  "findings": [{
    "category": "reliability",
    "severity": "medium",
    "title": "Report write may leave partial state",
    "explanation": "The inspected sequence writes related records separately; failure between writes may leave inconsistent state.",
    "recommendation": "Consider a transaction around the related writes and verify failure behavior.",
    "evidence": [{"path": "app/Services/ReportService.php", "start_line": 10, "end_line": 18}],
    "confidence": 0.7
  }]
}
```

## Invalid examples

These are mutations of the valid candidate; each independently rejects the entire candidate.

| JSON replacement/addition | Reason |
| --- | --- |
| `"schema_version": 2` | Unsupported schema |
| `"category": "performance"` | Unsupported category |
| `"severity": "urgent"` | Unsupported severity |
| `"title": "   "` | Empty trimmed title |
| `"recommendation": null` | Required non-null text |
| `"confidence": 1.1` or `"confidence": null` | Outside range or wrong type |
| `"evidence": []` | Missing evidence |
| `{"path":"../secret.txt","start_line":1,"end_line":1}` | Unsafe relative path |
| `{"path":"app/Services/ReportService.php","start_line":18,"end_line":10}` | Reversed range |
| `{"path":"app/Services/ReportService.php","start_line":0,"end_line":10}` | Zero-based location |
| `{"path":"app/Services/ReportService.php","start_line":19,"end_line":20}` | Outside fixture context |
| `"tool_call": "run tests"` added to finding | Unknown field |
| `"excerpt": "source"` added to evidence | Unknown field; source text not part of envelope |

Malformed JSON, duplicate JSON keys, 21 otherwise valid findings, oversized text, floating-point line numbers and paths absent from the context also fail. Trimming validates text length; persisted text uses that trimmed value. No other repair is allowed.
