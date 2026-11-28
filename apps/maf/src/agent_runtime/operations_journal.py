"""Append versioned, metadata-only runs from an explicitly configured local caller."""

import json
import logging
import os
import re
import stat
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from typing import BinaryIO
from uuid import uuid4

OPERATIONS_DIR_ENV = "WORKBENCH_AGENT_OPERATIONS_DIR"
OPERATIONS_SCOPE = "local-operator"
_CHECKOUT_JOURNAL = Path(".local/workbench-agent-operations")
_RUN_FILENAME = re.compile(r"[a-f0-9]{32}\.jsonl")
_MAX_RECORD_BYTES = 16_384
_MAX_RUN_BYTES = 8 * 1024 * 1024
_MAX_RUN_FILES = 256
_MAX_TERMINAL_RUNS = 100
_RETENTION = timedelta(days=30)
_LOGGER = logging.getLogger(__name__)


def local_directory(path: Path) -> Path:
    """Check the configured local path and each existing parent for redirections."""
    if not path.is_absolute() or path.drive.startswith("\\\\") or ".." in path.parts:
        raise OSError("Agent operations needs an absolute local directory")
    for folder in (*reversed(path.parents), path):
        entry = folder.lstat()
        if not stat.S_ISDIR(entry.st_mode) or _reparse(entry):
            raise OSError("Agent operations directory is unavailable")
    return path


def _reparse(entry: os.stat_result) -> bool:
    return bool(getattr(entry, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def read_operations_file(path: Path, *, limit: int = 65_536) -> bytes:
    """Read bounded safe metadata from a regular file in the configured directory."""
    entry = path.lstat()
    if not stat.S_ISREG(entry.st_mode) or _reparse(entry):
        raise OSError("Agent operations metadata must be a regular file")
    with path.open("rb") as stream:
        if not os.path.samestat(entry, os.fstat(stream.fileno())):
            raise OSError("Agent operations metadata changed")
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Agent operations metadata exceeds its limit")
    return raw


def operations_directory(environ: Mapping[str, str]) -> str | None:
    """Use an explicit override or discover the journal initialized by the checkout launcher."""
    configured = environ.get(OPERATIONS_DIR_ENV)
    if configured is not None:
        return configured or None
    source = Path(__file__).resolve()
    checkout = next(
        (parent for parent in source.parents if parent / "apps/maf/src/agent_runtime" == source.parent), None
    )
    if checkout is None:
        return None
    directory = checkout / _CHECKOUT_JOURNAL
    try:
        local_directory(directory / "runs")
        read_operations_file(directory / "catalog.json")
    except (OSError, ValueError):
        return None
    return str(directory)


def _ensure_local_directory(path: Path) -> None:
    try:
        local_directory(path)
    except FileNotFoundError:
        _ensure_local_directory(path.parent)
        path.mkdir(mode=0o700, exist_ok=True)
        local_directory(path)


def publish_operations_catalog(directory: Path, catalog: bytes) -> None:
    """Initialize the journal and atomically publish the runtime's metadata-only catalog."""
    _ensure_local_directory(directory / "runs")
    target = directory / "catalog.json"
    try:
        if read_operations_file(target) == catalog:
            return
    except FileNotFoundError:
        pass
    pending = None
    try:
        with NamedTemporaryFile(dir=directory, prefix=".catalog-", delete=False) as output:
            pending = Path(output.name)
            output.write(catalog)
            output.flush()
            os.fsync(output.fileno())
        os.replace(pending, target)
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


def _terminal_time(path: Path) -> datetime | None:
    if not _RUN_FILENAME.fullmatch(path.name):
        return None
    entry = path.lstat()
    if not stat.S_ISREG(entry.st_mode) or _reparse(entry) or entry.st_size > _MAX_RUN_BYTES:
        return None
    with path.open("rb") as stream:
        if not os.path.samestat(entry, os.fstat(stream.fileno())):
            return None
        stream.seek(max(0, entry.st_size - _MAX_RECORD_BYTES))
        tail = stream.read(_MAX_RECORD_BYTES)
    lines = tail.splitlines()
    if not lines or not tail.endswith(b"\n"):
        return None
    try:
        payload = json.loads(lines[-1])
        if (
            not isinstance(payload, dict)
            or payload.get("scope") != OPERATIONS_SCOPE
            or payload.get("run_id") != path.stem
            or payload.get("kind") != "run_finished"
        ):
            return None
        timestamp = datetime.fromisoformat(payload["timestamp"])
        return timestamp if timestamp.tzinfo else None
    except (ValueError, TypeError, KeyError, RecursionError):
        return None


def _prune(directory: Path) -> None:
    cutoff = datetime.now(UTC) - _RETENTION
    terminal: list[tuple[datetime, Path]] = []
    count = 0
    for path in directory.iterdir():
        count += 1
        if count > _MAX_RUN_FILES:
            raise OSError("Agent operations directory exceeds its limits")
        try:
            timestamp = _terminal_time(path)
            if timestamp is not None:
                terminal.append((timestamp, path))
        except FileNotFoundError:
            continue
    expired = [
        path
        for index, (timestamp, path) in enumerate(sorted(terminal, reverse=True))
        if index >= _MAX_TERMINAL_RUNS or timestamp < cutoff
    ]
    for path in expired:
        path.unlink(missing_ok=True)
    if count - len(expired) >= _MAX_RUN_FILES:
        raise OSError("Agent operations journal is full")


class OperationsJournal:
    """Own the sequence of one caller run, including concurrent case callbacks."""

    def __init__(self, stream: BinaryIO, run_id: str) -> None:
        self._stream = stream
        self._run_id = run_id
        self._sequence = 0
        self._lock = Lock()

    @classmethod
    def start(cls, configured_path: str | None, identity: Mapping[str, object]) -> "OperationsJournal | None":
        """Publish a frozen run identity or leave the underlying invocation independent."""
        if not configured_path:
            return None
        try:
            directory = local_directory(Path(configured_path)) / "runs"
            directory.mkdir(mode=0o700, exist_ok=True)
            local_directory(directory)
            _prune(directory)
            run_id = uuid4().hex
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
            handle = os.open(directory / f"{run_id}.jsonl", flags, 0o600)
            writer = cls(os.fdopen(handle, "wb"), run_id)
        except OSError:
            _LOGGER.warning("Agent operations journal unavailable")
            return None
        writer.emit("run_queued", stage="queued", run=dict(identity))
        writer.emit("run_started", stage="admission")
        return writer

    def emit(self, kind: str, **metadata: object) -> None:
        """Commit one complete bounded record from the caller's metadata allowlist."""
        with self._lock:
            if self._stream.closed:
                return
            event = {
                "schema_version": 1,
                "scope": OPERATIONS_SCOPE,
                "run_id": self._run_id,
                "sequence": self._sequence + 1,
                "timestamp": datetime.now(UTC).isoformat(),
                "kind": kind,
                **metadata,
            }
            try:
                record = json.dumps(event, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
                if len(record) > _MAX_RECORD_BYTES or self._stream.tell() + len(record) > _MAX_RUN_BYTES:
                    raise OSError("Agent operations journal exceeds its limits")
                self._stream.write(record)
                self._stream.flush()
                os.fsync(self._stream.fileno())
                self._sequence += 1
            except (OSError, ValueError, TypeError):
                self._close()
                _LOGGER.warning("Agent operations journal unavailable")
            if kind == "run_finished":
                self._close()

    def _close(self) -> None:
        try:
            self._stream.close()
        except OSError:
            pass
