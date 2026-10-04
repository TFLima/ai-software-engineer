"""Defensive streaming tar.gz extraction; never tarfile.extract/extractall.

Parse extension records explicitly so PAX/GNU headers cannot bypass budgets.
"""
import configparser
from dataclasses import dataclass
import gzip
import os
from pathlib import Path
import re
import tarfile
import unicodedata
import zlib

from app.acquisition import AcquisitionError, AcquisitionBudget


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    size: int
    omission: str | None = None


@dataclass(frozen=True)
class Snapshot:
    root: Path
    commit_sha: str
    files: tuple[ManifestEntry, ...]
    submodules: tuple[str, ...]
    limitations: tuple[str, ...]


def safe_path(value: str, limits, wrapper=False):
    if (not value or "\\" in value or value.startswith("/") or ":" in value
            or any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in value)):
        raise AcquisitionError("unsafe_snapshot")
    parts = value.rstrip("/").split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise AcquisitionError("unsafe_snapshot")
    # NFC aliases share an identity; collision is rejected by extraction.
    normalized = unicodedata.normalize("NFC", "/".join(parts))
    allowance = 1 if wrapper else 0
    if len(parts) > limits["path_depth"] + allowance:
        raise AcquisitionError("limit_exceeded")
    if len(normalized) > limits["path_characters"] + (512 if wrapper else 0):
        raise AcquisitionError("limit_exceeded")
    return normalized


def pax_fields(data):
    result = {}
    while data:
        match = re.match(rb"([1-9][0-9]*) ", data)
        if not match:
            raise AcquisitionError("unsafe_snapshot")
        length = int(match[1])
        if length > len(data) or length <= match.end() or data[length - 1:length] != b"\n":
            raise AcquisitionError("unsafe_snapshot")
        record = data[match.end():length - 1]
        if b"=" not in record:
            raise AcquisitionError("unsafe_snapshot")
        key, value = record.split(b"=", 1)
        key, value = key.decode("utf-8"), value.decode("utf-8")
        if key in result or key not in {"path", "mtime", "atime", "ctime", "comment",
                                        "uid", "gid", "uname", "gname"}:
            raise AcquisitionError("unsafe_snapshot")
        result[key] = value
        data = data[length:]
    return result


class TarStream:
    def __init__(self, stream, budget):
        self.stream, self.budget = stream, budget
        self.expanded = 0
        limits = budget.limits
        # Header/padding and bounded extension records count even when hidden by tar libraries.
        self.ceiling = limits["extracted_bytes"] + limits["archive_entries"] * 1024 + 65536

    def read(self, size):
        self.budget.remaining()
        data = self.stream.read(size)
        self.expanded += len(data)
        if self.expanded > self.ceiling:
            raise AcquisitionError("limit_exceeded")
        self.budget.remaining()
        return data

    def exact(self, size):
        data = self.read(size)
        if len(data) != size:
            raise AcquisitionError("unsafe_snapshot")
        return data


def extract(archive: Path, root: Path, sha: str, budget: AcquisitionBudget) -> Snapshot:
    limits = budget.limits
    files = []
    seen = set()
    wrapper = None
    entries = extracted = metadata = 0
    pending = None
    try:
        with gzip.open(archive, "rb") as compressed:
            stream = TarStream(compressed, budget)
            while True:
                header = stream.exact(512)
                if header == bytes(512):
                    if stream.exact(512) != bytes(512) or pending is not None:
                        raise AcquisitionError("unsafe_snapshot")
                    # Consume the gzip trailer/CRC and reject extra tar content.
                    while chunk := stream.read(16384):
                        if any(chunk):
                            raise AcquisitionError("unsafe_snapshot")
                    break
                entries += 1
                if entries > limits["archive_entries"]:
                    raise AcquisitionError("limit_exceeded")
                member = tarfile.TarInfo.frombuf(header, "utf-8", "strict")
                if member.size < 0:
                    raise AcquisitionError("unsafe_snapshot")
                if member.type in (tarfile.XHDTYPE, tarfile.XGLTYPE, tarfile.GNUTYPE_LONGNAME):
                    if member.size > 8192:
                        raise AcquisitionError("limit_exceeded")
                    metadata += member.size
                    if metadata > 65536 or pending is not None:
                        raise AcquisitionError("limit_exceeded")
                    data = stream.exact(member.size)
                    stream.exact((-member.size) % 512)
                    if member.type == tarfile.GNUTYPE_LONGNAME:
                        if not data.endswith(b"\0"):
                            raise AcquisitionError("unsafe_snapshot")
                        pending = data[:-1].decode("utf-8")
                    else:
                        fields = pax_fields(data)
                        if member.type == tarfile.XGLTYPE:
                            if "path" in fields:
                                raise AcquisitionError("unsafe_snapshot")
                        else:
                            pending = fields.get("path", member.name)
                            # Non-path extensions must leave the following name unchanged.
                            if "path" not in fields:
                                pending = ""
                    continue
                name = pending or member.name
                pending = None
                full = safe_path(name, limits, wrapper=True)
                parts = full.split("/")
                if wrapper is None:
                    wrapper = parts[0]
                if parts[0] != wrapper:
                    raise AcquisitionError("unsafe_snapshot")
                if member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE):
                    raise AcquisitionError("unsafe_snapshot")
                if len(parts) == 1:
                    if not member.isdir() or member.size:
                        raise AcquisitionError("unsafe_snapshot")
                    continue
                path = safe_path("/".join(parts[1:]), limits)
                if path in seen:
                    raise AcquisitionError("unsafe_snapshot")
                seen.add(path)
                destination = root.joinpath(*path.split("/"))
                if member.isdir():
                    if member.size:
                        raise AcquisitionError("unsafe_snapshot")
                    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
                    continue
                if len(files) >= limits["file_count"] or member.size > limits["file_bytes"]:
                    raise AcquisitionError("limit_exceeded")
                extracted += member.size
                if extracted > limits["extracted_bytes"]:
                    raise AcquisitionError("limit_exceeded")
                destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                # Ignore archive permissions, owners and timestamps. No executable bits.
                fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                prefix = b""
                with os.fdopen(fd, "wb") as out:
                    remaining = member.size
                    while remaining:
                        data = stream.exact(min(16384, remaining))
                        out.write(data)
                        prefix = (prefix + data)[:256]
                        remaining -= len(data)
                stream.exact((-member.size) % 512)
                omission = None
                if prefix.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
                    omission = "lfs"
                    destination.unlink()
                files.append(ManifestEntry(path, member.size, omission))
    except AcquisitionError:
        raise
    except (tarfile.TarError, EOFError, OSError, ValueError, UnicodeError, zlib.error):
        raise AcquisitionError("unsafe_snapshot") from None
    if wrapper is None:
        raise AcquisitionError("unsafe_snapshot")
    submodules, limitations = submodule_paths(root, limits)
    for i, entry in enumerate(files):
        if any(entry.path == path or entry.path.startswith(path + "/") for path in submodules):
            if entry.omission is None:
                root.joinpath(entry.path).unlink()
            files[i] = ManifestEntry(entry.path, entry.size, "submodule")
    if any(entry.omission == "lfs" for entry in files):
        limitations.append("Git LFS objects were not fetched; pointer files were omitted")
    budget.remaining()
    return Snapshot(root, sha, tuple(sorted(files, key=lambda f: f.path)),
                    tuple(submodules), tuple(limitations))


def submodule_paths(root, limits):
    config = root / ".gitmodules"
    if not config.is_file():
        return [], []
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    try:
        parser.read_string(config.read_text(encoding="utf-8"))
        paths = sorted({safe_path(parser[section]["path"].strip().strip('"'), limits)
                        for section in parser.sections() if section.startswith('submodule "')
                        and "path" in parser[section]})
    except (configparser.Error, UnicodeError):
        return [], ["Submodule configuration could not be inventoried; no dependencies were fetched"]
    return paths, (["Submodules were not fetched; directory-only dependencies are outside the file inventory"]
                   if paths else [])
