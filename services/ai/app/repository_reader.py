"""B05 public GitHub acquisition, independent of the B10 orchestrator."""
from contextlib import asynccontextmanager
import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import logging
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, urljoin

from app.acquisition import AcquisitionBudget, AcquisitionError
from app.github_transport import GitHubTransport, target
from app.snapshot import extract

SHA = re.compile(r"[0-9a-f]{40}\Z")
LOG = logging.getLogger(__name__)


def identity(repository):
    if type(repository) is not dict or repository.keys() != {"owner", "name", "url"}:
        raise AcquisitionError("invalid_request")
    owner, name = repository["owner"], repository["name"]
    if (type(owner) is not str or type(name) is not str
            or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?", owner)
            or "--" in owner or not re.fullmatch(r"[a-z0-9._-]{1,100}", name)
            or name in (".", "..") or repository["url"] != f"https://github.com/{owner}/{name}"):
        raise AcquisitionError("invalid_request")
    return owner, name


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def retry_delay(headers):
    """Trust quota timing only as a lower bound, never as permission to extend a deadline."""
    delay = 0.0
    now = datetime.now(timezone.utc)
    value = headers.get("retry-after")
    if value is not None:
        try:
            delay = float(value) if re.fullmatch(r"[0-9]+", value) else (
                parsedate_to_datetime(value) - now).total_seconds()
        except (ValueError, TypeError, OverflowError):
            delay = 60.0
    if headers.get("x-ratelimit-remaining") == "0":
        try:
            delay = max(delay, float(int(headers["x-ratelimit-reset"])) - now.timestamp() + 1)
        except (KeyError, ValueError, OverflowError):
            delay = max(delay, 60.0)
    return max(0.0, delay)


def secondary_limit(body):
    try:
        message = json.loads(body).get("message", "")
        return type(message) is str and any(marker in message.lower()
            for marker in ("secondary rate limit", "rate limit exceeded"))
    except (ValueError, AttributeError, UnicodeError, RecursionError):
        return False


class RepositoryReader:
    def __init__(self, transport=None, workspace_parent: Path | None = None):
        self.transport = transport or GitHubTransport()
        self.workspace_parent = workspace_parent
        # Reuse one reader in B10: quota cooldowns survive new invocations in this process.
        self.cooldowns = {}

    @asynccontextmanager
    async def snapshot(self, repository: dict, commit_sha: str | None, limits: dict,
                       deadline: datetime, on_sha=None):
        owner, name = identity(repository)
        if commit_sha is not None and (type(commit_sha) is not str or not SHA.fullmatch(commit_sha)):
            raise AcquisitionError("invalid_request")
        budget = AcquisitionBudget.start(limits, deadline)
        workspace = Path(tempfile.mkdtemp(prefix="ase-snapshot-", dir=self.workspace_parent))
        try:
            root = workspace / "source"
            root.mkdir(mode=0o700)
            base = f"https://api.github.com/repos/{owner}/{name}"
            metadata = await self.metadata(base, budget)
            if (metadata.get("private") is not False or metadata.get("visibility") != "public"
                    or type(metadata.get("full_name")) is not str
                    or metadata["full_name"].lower() != f"{owner}/{name}"):
                raise AcquisitionError("repository_unavailable")
            if commit_sha is None:
                branch = metadata.get("default_branch")
                if type(branch) is not str or not branch or len(branch) > 255:
                    raise AcquisitionError("repository_unavailable")
                # Encode branch names as one path component; never use upstream URLs.
                head = await self.metadata(base + "/commits/" + quote(branch, safe=""), budget)
                commit_sha = head.get("sha")
                if type(commit_sha) is not str or not SHA.fullmatch(commit_sha):
                    raise AcquisitionError("repository_unavailable")
            if on_sha is not None:
                on_sha(commit_sha)
            archive = workspace / "archive.tar.gz"
            url = f"https://codeload.github.com/{owner}/{name}/tar.gz/{commit_sha}"
            await self.download(url, archive, budget)
            result = extract(archive, root, commit_sha, budget)
            archive.unlink()
            yield result
        except AcquisitionError as error:
            error.commit_sha = commit_sha
            raise
        finally:
            try:
                await asyncio.wait_for(asyncio.to_thread(shutil.rmtree, workspace),
                                       timeout=limits["cleanup_seconds"])
            except (OSError, TimeoutError):
                # B12 owns scheduled stale cleanup. Never leak source paths or exception text.
                LOG.error("snapshot_cleanup_failed", extra={"code": "snapshot_cleanup_failed"})

    async def metadata(self, url, budget):
        data = await self.fetch(url, budget, 1048576)
        try:
            result = json.loads(data.decode("utf-8"), object_pairs_hook=unique_pairs,
                                parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if type(result) is not dict:
                raise ValueError
            return result
        except (ValueError, UnicodeError, RecursionError):
            raise AcquisitionError("repository_unavailable") from None

    async def download(self, url, destination, budget):
        await self.fetch(url, budget, budget.limits["archive_bytes"], destination)

    async def fetch(self, url, budget, maximum, destination=None):
        original = url
        for attempt in range(budget.limits["operation_tries"]):
            url, redirects = original, 0
            expires = None
            wait = budget.limits["operation_backoff_seconds"] * (2 ** attempt)
            try:
                while True:
                    host = target(url).hostname
                    cooldown = self.cooldowns.get(host, 0) - time.monotonic()
                    if cooldown > 0:
                        await budget.wait(cooldown, "upstream_rate_limited")
                    if expires is None:
                        expires = min(budget.expires, time.monotonic() + budget.limits["github_request_seconds"])
                    async with self.transport.get(url, budget, expires) as response:
                        status, headers = response.status, response.headers
                        # Bodies of errors/redirects also count toward the total transfer cap.
                        total = 0
                        body = bytearray()
                        out = (os.fdopen(os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                                                 0o600), "wb")
                               if destination is not None and status == 200 else None)
                        try:
                            async for chunk in response.chunks():
                                total += len(chunk)
                                if total > (maximum if status == 200 else min(maximum, 1048576)):
                                    raise AcquisitionError("limit_exceeded")
                                if out is not None:
                                    out.write(chunk)
                                elif status in (200, 403):
                                    body.extend(chunk)
                        finally:
                            if out is not None:
                                out.close()
                        if status in (301, 302, 303, 307, 308):
                            if redirects >= budget.limits["redirects"] or "location" not in headers:
                                raise AcquisitionError("unsafe_snapshot")
                            url = urljoin(url, headers["location"])
                            target(url)
                            redirects += 1
                            continue
                        limited = status == 429 or (status == 403 and (
                            headers.get("x-ratelimit-remaining") == "0" or "retry-after" in headers
                            or secondary_limit(body)))
                        if limited:
                            wait = max(wait, retry_delay(headers) or 60)
                            self.cooldowns[host] = time.monotonic() + wait
                            raise AcquisitionError("upstream_rate_limited")
                        if status == 200:
                            # Honor exhausted quotas even after a successful metadata request.
                            if headers.get("x-ratelimit-remaining") == "0":
                                self.cooldowns[host] = time.monotonic() + max(1, retry_delay(headers))
                            return bytes(body)
                        if status in (401, 403, 404, 410, 422):
                            raise AcquisitionError("repository_unavailable")
                        if 500 <= status <= 599:
                            raise AcquisitionError("upstream_unavailable")
                        raise AcquisitionError("repository_unavailable")
            except AcquisitionError as error:
                if not error.retryable or attempt + 1 >= budget.limits["operation_tries"]:
                    raise
                await budget.wait(wait, error.code)
        raise AssertionError("Unreachable")
