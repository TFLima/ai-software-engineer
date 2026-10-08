"""B09 whole-candidate validation against trusted B07 context, without repair."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import re
import time
import unicodedata

from app.context_builder import ContextResult, Coverage, IncludedSpan
from app.limits import CEILINGS


def pairs(entries):
    result = {}
    for key, value in entries:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def bad_constant(_):
    raise ValueError


class FindingError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ValidatedFindings:
    schema_version: int
    findings: tuple[dict, ...]
    coverage: Coverage


def require(condition):
    if not condition:
        raise FindingError("invalid_findings")


def path_valid(path, limits):
    return (type(path) is str and 1 <= len(path) <= limits["path_characters"]
            and not path.endswith("/") and "\\" not in path
            and not re.match(r"^[A-Za-z]:", path)
            and not any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in path)
            and len(path.split("/")) <= limits["path_depth"]
            and all(part not in ("", ".", "..") for part in path.split("/")))


def text(value, maximum, multiline=True):
    require(type(value) is str)
    require(not any(unicodedata.category(c) in {"Cc", "Cs"}
                    and not (multiline and c in "\n\t") for c in value))
    value = value.strip()
    require(1 <= len(value) <= maximum)
    return value


class FindingValidator:
    def validate(self, candidate_json: str, context: ContextResult,
                 limits: dict[str, int], deadline: datetime) -> ValidatedFindings:
        if (type(limits) is not dict or limits.keys() != CEILINGS.keys()
                or any(type(v) is not int or not 0 < v <= CEILINGS[k] for k, v in limits.items())
                or not isinstance(deadline, datetime) or deadline.tzinfo is None
                or type(context) is not ContextResult or type(context.coverage) is not Coverage):
            raise FindingError("invalid_request")
        available = (deadline - datetime.now(timezone.utc)).total_seconds() - limits["cleanup_seconds"]
        expires = time.monotonic() + min(limits["validate_seconds"], available)

        def check():
            if (time.monotonic() >= expires or
                    (deadline - datetime.now(timezone.utc)).total_seconds() <= limits["cleanup_seconds"]):
                raise FindingError("limit_exceeded")

        check()
        if context.policy_version != "1":
            raise FindingError("unsupported_schema")
        coverage = context.coverage
        if (type(context.text) is not str or type(context.rendered_bytes) is not int
                or type(context.context_tokens) is not int or context.context_tokens < 0
                or type(coverage.included_spans) is not tuple
                or any(type(v) is not int or v < 0 for v in (
                    coverage.inventory_files, coverage.eligible_files, coverage.included_files,
                    coverage.included_lines, coverage.omitted_files))):
            raise FindingError("invalid_request")
        if not context.text or not coverage.included_spans or not coverage.included_lines:
            raise FindingError("no_eligible_context")
        try:
            rendered_bytes = len(context.text.encode("utf-8"))
        except UnicodeError:
            raise FindingError("invalid_request") from None
        if context.rendered_bytes != rendered_bytes:
            raise FindingError("invalid_request")
        if (len(coverage.included_spans) > limits["context_spans"]
                or coverage.included_files > limits["context_files"]
                or rendered_bytes > limits["context_bytes"]
                or context.context_tokens > limits["context_tokens"]):
            raise FindingError("limit_exceeded")
        spans = {}
        for span in coverage.included_spans:
            check()
            if (type(span) is not IncludedSpan or not path_valid(span.path, limits)
                    or type(span.start_line) is not int or type(span.end_line) is not int
                    or not 1 <= span.start_line <= span.end_line):
                raise FindingError("invalid_request")
            spans.setdefault(span.path, []).append((span.start_line, span.end_line))
        total = 0
        for ranges in spans.values():
            ranges.sort()
            previous = 0
            for start, end in ranges:
                if start <= previous:
                    raise FindingError("invalid_request")
                total += end - start + 1
                previous = end
        if (len(spans) != coverage.included_files or total != coverage.included_lines
                or not coverage.included_files <= coverage.eligible_files <= coverage.inventory_files
                or coverage.inventory_files > limits["file_count"]
                or coverage.omitted_files != coverage.inventory_files - coverage.included_files):
            raise FindingError("invalid_request")
        require(type(candidate_json) is str)
        try:
            size = len(candidate_json.encode("utf-8"))
        except UnicodeError:
            raise FindingError("invalid_findings") from None
        if size > limits["internal_response_bytes"]:
            raise FindingError("limit_exceeded")
        try:
            candidate = json.loads(candidate_json, object_pairs_hook=pairs, parse_constant=bad_constant)
        except (ValueError, UnicodeError, RecursionError):
            raise FindingError("invalid_findings") from None
        check()
        require(type(candidate) is dict and candidate.keys() == {"schema_version", "findings"})
        require(type(candidate["schema_version"]) is int and candidate["schema_version"] == 1)
        findings = candidate["findings"]
        require(type(findings) is list and len(findings) <= limits["max_findings"])
        validated = []
        required = {"category", "severity", "title", "explanation", "recommendation", "evidence"}
        for finding in findings:
            check()
            require(type(finding) is dict and required <= finding.keys()
                    and finding.keys() <= required | {"confidence"})
            require(type(finding["category"]) is str and finding["category"] in
                    {"architecture", "maintainability", "reliability", "security", "testing"})
            require(type(finding["severity"]) is str and finding["severity"] in
                    {"info", "low", "medium", "high", "critical"})
            result = {**finding, "title": text(finding["title"], 160, False),
                      "explanation": text(finding["explanation"], 4000),
                      "recommendation": text(finding["recommendation"], 2000)}
            if "confidence" in finding:
                value = finding["confidence"]
                require(type(value) in (int, float) and 0 <= value <= 1 and math.isfinite(value))
            evidence = finding["evidence"]
            require(type(evidence) is list and 1 <= len(evidence) <= limits["evidence_per_finding"])
            seen = set()
            for entry in evidence:
                check()
                require(type(entry) is dict and entry.keys() == {"path", "start_line", "end_line"})
                path, start, end = entry["path"], entry["start_line"], entry["end_line"]
                require(path_valid(path, limits) and type(start) is int and type(end) is int
                        and 1 <= start <= end)
                identity = (path, start, end)
                require(identity not in seen)
                seen.add(identity)
                next_line = start
                for low, high in spans.get(path, []):
                    if low > next_line:
                        break
                    if high >= next_line:
                        next_line = high + 1
                    if next_line > end:
                        break
                require(next_line > end)
            validated.append(result)
        check()
        return ValidatedFindings(1, tuple(validated), coverage)
