"""Shared, source-free errors and frozen acquisition budgets."""
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import time

from app.limits import CEILINGS


class AcquisitionError(Exception):
    def __init__(self, code: str, commit_sha: str | None = None):
        super().__init__(code)
        self.code = code
        self.commit_sha = commit_sha
        self.retryable = code in {"network_unavailable", "upstream_unavailable",
                                  "upstream_timeout", "upstream_rate_limited"}


@dataclass
class AcquisitionBudget:
    limits: dict[str, int]
    expires: float
    requests: int = 0
    downloaded: int = 0

    @classmethod
    def start(cls, limits: dict[str, int], deadline: datetime):
        # Independently defend direct component use, not just HTTP entry points.
        if type(limits) is not dict or limits.keys() != CEILINGS.keys() or any(
            type(v) is not int or not 0 < v <= CEILINGS[k] for k, v in limits.items()
        ):
            raise AcquisitionError("invalid_request")
        if not isinstance(deadline, datetime) or deadline.tzinfo is None:
            raise AcquisitionError("invalid_request")
        if (limits["archive_bytes"] > limits["download_bytes"]
                or limits["file_bytes"] > limits["extracted_bytes"]):
            raise AcquisitionError("invalid_request")
        available = (deadline - datetime.now(timezone.utc)).total_seconds()
        duration = min(limits["acquire_seconds"], available - limits["cleanup_seconds"])
        if duration <= 0:
            raise AcquisitionError("upstream_timeout")
        return cls(dict(limits), time.monotonic() + duration)

    def remaining(self):
        remaining = self.expires - time.monotonic()
        if remaining <= 0:
            raise AcquisitionError("upstream_timeout")
        return remaining

    def request(self):
        self.remaining()
        if self.requests >= self.limits["github_requests"]:
            raise AcquisitionError("limit_exceeded")
        self.requests += 1

    def consume(self, count: int):
        self.remaining()
        self.downloaded += count
        if self.downloaded > self.limits["download_bytes"]:
            raise AcquisitionError("limit_exceeded")

    async def wait(self, seconds: float, code="upstream_timeout"):
        if seconds >= self.remaining():
            raise AcquisitionError(code)
        await asyncio.sleep(seconds)
        self.remaining()
