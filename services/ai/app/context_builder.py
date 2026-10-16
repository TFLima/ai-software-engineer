"""B07 bounded, deterministic repository context and exact evidence coverage."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import time
from typing import Callable

from app.acquisition import AcquisitionError
from app.file_selector import (POLICY_VERSION as SELECTION_VERSION, REASONS,
                               OmissionSummary, SelectionDecision,
                               SelectionError, SelectionResult, content_reason,
                               path_reason, read_snapshot_file)
from app.limits import CEILINGS
from app.snapshot import ManifestEntry, Snapshot, safe_path

POLICY_VERSION = "1"
STATIC_LIMITATION = "Static inspection of selected context only"
TRUNCATION_LIMITATION = "Some selected files were partially included due to context limits"
OMISSION_LIMITATION = "Some repository files were omitted from context"
SUBMODULE_LIMITATION = "Directory-only submodules were not inspected"


class ContextError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class IncludedSpan:
    path: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class Coverage:
    inventory_files: int
    eligible_files: int
    included_files: int
    included_lines: int
    omitted_files: int
    included_spans: tuple[IncludedSpan, ...]
    omissions: tuple[OmissionSummary, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class ContextResult:
    policy_version: str
    text: str
    rendered_bytes: int
    context_tokens: int
    coverage: Coverage


class ContextBuilder:
    def build(self, snapshot: Snapshot, selection: SelectionResult,
              limits: dict[str, int], deadline: datetime,
              token_counter: Callable[[str], int] | None = None) -> ContextResult:
        if (type(snapshot) is not Snapshot or type(selection) is not SelectionResult
                or selection.policy_version != SELECTION_VERSION
                or type(limits) is not dict or limits.keys() != CEILINGS.keys()
                or any(type(value) is not int or not 0 < value <= CEILINGS[key]
                       for key, value in limits.items())
                or not isinstance(deadline, datetime) or deadline.tzinfo is None
                or (token_counter is not None and not callable(token_counter))):
            raise ContextError("invalid_request")
        available = (deadline - datetime.now(timezone.utc)).total_seconds()
        duration = min(limits["context_seconds"], available - limits["cleanup_seconds"])
        if duration <= 0:
            raise ContextError("limit_exceeded")
        expires = time.monotonic() + duration
        self._validate_selection(snapshot, selection, limits)

        chunks: list[str] = []
        rendered_bytes = 0
        counted_tokens = 0
        spans: list[IncludedSpan] = []
        omitted = {reason: 0 for reason in REASONS}
        partial = False
        manifest = {entry.path: entry for entry in snapshot.files}

        for decision in selection.entries:
            self._check(expires)
            if decision.reason is not None:
                omitted[decision.reason] += 1
                continue
            if (len(spans) >= limits["context_files"]
                    or len(spans) >= limits["context_spans"]):
                omitted["context_budget"] += 1
                continue
            try:
                data = read_snapshot_file(snapshot.root, manifest[decision.path], limits, expires)
            except SelectionError as error:
                raise ContextError(error.code) from None
            if content_reason(data) is not None:
                raise ContextError("unsafe_snapshot")
            lines = data.decode("utf-8").split("\n")
            if lines[-1] == "":
                lines.pop()  # A trailing newline does not create an extra source line.
            header = f"FILE {json.dumps(decision.path, ensure_ascii=False)}\n"
            file_lines: list[str] = []
            for number, source_line in enumerate(lines, start=1):
                self._check(expires)
                labeled_line = f"{number}: {source_line}\n"
                addition = (header if not file_lines else "") + labeled_line
                candidate_bytes = rendered_bytes + len(addition.encode("utf-8"))
                if candidate_bytes > limits["context_bytes"]:
                    break
                if token_counter is None:
                    candidate_tokens = candidate_bytes  # Conservative fallback.
                else:
                    candidate_tokens = self._count(token_counter, "".join(chunks) +
                                                   header + "".join(file_lines) + labeled_line)
                    self._check(expires)
                if candidate_tokens > limits["context_tokens"]:
                    break
                rendered_bytes = candidate_bytes
                counted_tokens = candidate_tokens
                file_lines.append(labeled_line)
            if file_lines:
                chunks.append(header)
                chunks.extend(file_lines)
                spans.append(IncludedSpan(decision.path, 1, len(file_lines)))
                partial |= len(file_lines) < len(lines)
            else:
                omitted["context_budget"] += 1

        self._check(expires)
        if not spans:
            raise ContextError("no_eligible_context")
        omissions = tuple(OmissionSummary(reason, omitted[reason]) for reason in REASONS
                          if omitted[reason])
        limitations = [STATIC_LIMITATION]
        if partial:
            limitations.append(TRUNCATION_LIMITATION)
        if omissions:
            limitations.append(OMISSION_LIMITATION)
        if snapshot.submodules:
            limitations.append(SUBMODULE_LIMITATION)
        coverage = Coverage(
            inventory_files=selection.inventory_files,
            eligible_files=selection.eligible_files,
            included_files=len(spans),
            included_lines=sum(span.end_line - span.start_line + 1 for span in spans),
            omitted_files=selection.inventory_files - len(spans),
            included_spans=tuple(spans),
            omissions=omissions,
            limitations=tuple(limitations),
        )
        return ContextResult(POLICY_VERSION, "".join(chunks), rendered_bytes,
                             counted_tokens, coverage)

    @staticmethod
    def _count(counter: Callable[[str], int], text: str) -> int:
        try:
            value = counter(text)
        except Exception:
            raise ContextError("configuration_error") from None
        if type(value) is not int or value < 0:
            raise ContextError("configuration_error")
        return value

    @staticmethod
    def _check(expires: float) -> None:
        if time.monotonic() >= expires:
            raise ContextError("limit_exceeded")

    @staticmethod
    def _validate_selection(snapshot: Snapshot, selection: SelectionResult,
                            limits: dict[str, int]) -> None:
        if (len(snapshot.files) > limits["file_count"]
                or len(snapshot.files) != len(selection.entries)
                or any(type(item) is not ManifestEntry or type(item.path) is not str
                       or type(item.size) is not int for item in snapshot.files)
                or any(type(item) is not SelectionDecision or type(item.path) is not str
                       or type(item.size) is not int or item.reason not in (*REASONS, None)
                       for item in selection.entries)):
            raise ContextError("unsafe_snapshot")
        expected = sorted((item.path, item.size) for item in snapshot.files)
        actual = [(item.path, item.size) for item in selection.entries]
        if actual != expected or len({path for path, _ in expected}) != len(expected):
            raise ContextError("unsafe_snapshot")
        total_bytes = 0
        for decision, item in zip(selection.entries,
                                  sorted(snapshot.files, key=lambda entry: entry.path)):
            try:
                normalized = safe_path(item.path, limits)
            except AcquisitionError as error:
                raise ContextError(error.code) from None
            if (normalized != item.path or item.size < 0
                    or item.omission not in (None, "lfs", "submodule")):
                raise ContextError("unsafe_snapshot")
            if item.size > limits["file_bytes"]:
                raise ContextError("limit_exceeded")
            total_bytes += item.size
            if total_bytes > limits["extracted_bytes"]:
                raise ContextError("limit_exceeded")
            if item.omission is not None and decision.reason != item.omission:
                raise ContextError("unsafe_snapshot")
            if decision.reason is None and path_reason(decision.path) is not None:
                raise ContextError("unsafe_snapshot")
