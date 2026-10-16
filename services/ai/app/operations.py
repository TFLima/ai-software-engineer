"""Safe operational events and bounded cleanup of platform-owned workspaces."""
from contextvars import ContextVar
import json
import logging
from pathlib import Path
import re
import shutil
import tempfile
import time

CORRELATION = ContextVar("analysis_correlation", default={})
WORKSPACE_ROOT = Path(tempfile.gettempdir()) / "ase-workspaces"
STALE_SECONDS = 3600  # exceeds every invocation/deadline and its cleanup allowance
LOG = logging.getLogger("ase.operations")
if not LOG.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOG.addHandler(handler)
LOG.setLevel(logging.INFO)
LOG.propagate = True


def event(name, **fields):
    allowed = {"analysis_id", "attempt_id", "outcome", "code", "stage",
               "stage_durations_ms", "usage", "deleted", "failed"}
    LOG.info(json.dumps({"event": name, **CORRELATION.get(),
                         **{key: value for key, value in fields.items() if key in allowed}},
                        separators=(",", ":")))


def workspace_root():
    WORKSPACE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    if WORKSPACE_ROOT.is_symlink() or not WORKSPACE_ROOT.is_dir():
        raise RuntimeError("Invalid workspace root")
    return WORKSPACE_ROOT


def cleanup_stale(root=None, now=None):
    """Caller holds the endpoint slot; symlinks and unrelated entries are untouched.

    Only immediate platform-created directories older than one hour are eligible.
    Never traverse a link to delete another location. Limit each pass to 100 deletion attempts and a 10-second scan budget.
    """
    root = root or workspace_root()
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("Invalid workspace root")
    now = time.time() if now is None else now
    deleted = failed = 0
    started = time.monotonic()
    for entry in root.iterdir():
        if deleted + failed >= 100 or time.monotonic() - started >= 10:
            break
        if not re.fullmatch(r"ase-snapshot-[a-z0-9_]{8}", entry.name):
            continue
        try:
            if entry.is_symlink() or not entry.is_dir() or now - entry.stat().st_mtime < STALE_SECONDS:
                continue
            shutil.rmtree(entry)
            deleted += 1
        except OSError:
            failed += 1
    if deleted or failed:
        event("stale_workspace_cleanup", deleted=deleted, failed=failed)
    return deleted, failed
