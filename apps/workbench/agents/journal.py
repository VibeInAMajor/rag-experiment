"""Bounded access to version 1 metadata files in one operator-owned directory."""

import json
import os
import stat
import tempfile
from collections.abc import Callable
from contextlib import suppress
from functools import lru_cache
from itertools import islice
from pathlib import Path
from typing import Literal

from filelock import FileLock, Timeout
from pydantic import Field, TypeAdapter, field_validator

from apps.workbench.contracts.schemas import (
    AgentDefinition,
    AgentEvent,
    AgentRunId,
    AgentScope,
    AgentSelection,
    ContractModel,
    Identifier,
)

_MAX_CATALOG_BYTES = 128 * 1024
_MAX_SELECTION_BYTES = 16 * 1024
_MAX_EVENT_BYTES = 16 * 1024
_MAX_RUN_BYTES = 8 * 1024 * 1024
_MAX_RUN_FILES = 256
_RUN_ID = TypeAdapter(AgentRunId)


class AgentOperationsFailure(Exception):
    """A safe public error code and status for the local operations bridge."""

    def __init__(self, code: str, status: int = 503) -> None:
        self.code = code
        self.status = status
        super().__init__(code)


class _DiskRecord(ContractModel):
    schema_version: Literal[1]
    scope: AgentScope

    @field_validator("schema_version", mode="before")
    @classmethod
    def _integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Schema version must be an integer")
        return value


class CatalogFile(_DiskRecord):
    """Registry exported by the independent agent runtime."""

    agents: list[AgentDefinition] = Field(min_length=1, max_length=24)

    @field_validator("agents")
    @classmethod
    def _unique_agents(cls, agents: list[AgentDefinition]) -> list[AgentDefinition]:
        if len({agent.agent_id for agent in agents}) != len(agents):
            raise ValueError("Agent identifiers must be distinct")
        return agents


class SelectionFile(_DiskRecord):
    """Authoritative default selections for future eligible local runs."""

    selections: dict[Identifier, AgentSelection] = Field(max_length=24)


def _unique_members(pairs: list[tuple[str, object]]) -> dict[str, object]:
    distinct: dict[str, object] = {}
    for key, value in pairs:
        if key in distinct:
            raise ValueError("Repeated JSON member")
        distinct[key] = value
    return distinct


def _invalid_constant(_value: str) -> object:
    raise ValueError("Invalid JSON number")


def _decode(raw: bytes) -> object:
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_members, parse_constant=_invalid_constant)


def _local_directory(path: Path) -> Path:
    if not path.is_absolute() or path.drive.startswith("\\\\") or ".." in path.parts:
        raise OSError("Operations requires a regular local directory")
    for parent in (*reversed(path.parents), path):
        entry = parent.lstat()
        if not stat.S_ISDIR(entry.st_mode) or _is_reparse_point(entry):
            raise OSError("Operations requires a regular local directory")
    return path


def _is_reparse_point(entry: os.stat_result) -> bool:
    return bool(getattr(entry, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _regular_file(path: Path) -> os.stat_result:
    entry = path.lstat()
    if not stat.S_ISREG(entry.st_mode) or _is_reparse_point(entry):
        raise OSError("Operations requires a regular local file")
    return entry


def _read_file(path: Path, maximum: int, stat_before: os.stat_result) -> bytes:
    if stat_before.st_size > maximum:
        raise ValueError("Metadata exceeds its byte bound")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as metadata:
        opened = os.fstat(metadata.fileno())
        if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(stat_before, opened):
            raise OSError("Metadata was replaced during read")
        raw = metadata.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError("Metadata exceeds its byte bound")
    return raw


def _read_events(path: Path, stat_before: os.stat_result, content_revision: int) -> tuple[AgentEvent, ...]:
    # The revision keys restarts of the cache even when stat's coarse tuple compares equal.
    del content_revision
    raw = _read_file(path, _MAX_RUN_BYTES, stat_before)
    events: dict[int, AgentEvent] = {}
    # A concurrently appended unterminated line has not been committed by the caller.
    for line in raw.split(b"\n")[:-1]:
        if len(line) > _MAX_EVENT_BYTES:
            raise ValueError("Metadata event exceeds its byte bound")
        decoded = _decode(line)
        if not isinstance(decoded, dict) or type(decoded.get("schema_version")) is not int:
            raise ValueError("Metadata event has an invalid version")
        event = AgentEvent.model_validate(decoded)
        if event.run_id != path.stem:
            raise ValueError("Metadata event belongs to a different run")
        prior = events.get(event.sequence)
        if prior is not None and prior != event:
            raise ValueError("Metadata sequence has conflicting contents")
        events[event.sequence] = event

    # Show the committed prefix only. A missing sequence can arrive in a later read.
    contiguous: list[AgentEvent] = []
    for sequence in range(1, len(events) + 1):
        if sequence not in events:
            break
        contiguous.append(events[sequence])
    return tuple(contiguous)


class AgentJournal:
    """Read caller metadata and compare-and-swap the separate selected-default file."""

    def __init__(self, root: str | None) -> None:
        self._root = Path(root) if root is not None else None
        self._events = lru_cache(maxsize=8)(_read_events)

    def _directory(self) -> Path:
        if self._root is None:
            raise AgentOperationsFailure("AGENT_OPERATIONS_UNAVAILABLE")
        try:
            return _local_directory(self._root)
        except (OSError, RuntimeError):
            raise AgentOperationsFailure("AGENT_OPERATIONS_UNAVAILABLE") from None

    def _history(self) -> Path:
        root = self._directory()
        try:
            return _local_directory(root / "runs")
        except (OSError, RuntimeError):
            raise AgentOperationsFailure("AGENT_HISTORY_UNAVAILABLE") from None

    def history_available(self) -> bool:
        """Report whether the explicitly configured caller history directory is accessible."""
        try:
            self._history()
        except AgentOperationsFailure:
            return False
        return True

    def catalog(self) -> CatalogFile:
        """Read a schema-checked catalog without starting the runtime."""
        path = self._directory() / "catalog.json"
        try:
            return CatalogFile.model_validate(_decode(_read_file(path, _MAX_CATALOG_BYTES, _regular_file(path))))
        except (OSError, ValueError, RecursionError):
            raise AgentOperationsFailure("AGENT_OPERATIONS_UNAVAILABLE") from None

    def _selection(self, path: Path) -> SelectionFile:
        try:
            return SelectionFile.model_validate(_decode(_read_file(path, _MAX_SELECTION_BYTES, _regular_file(path))))
        except FileNotFoundError:
            return SelectionFile(schema_version=1, scope="local-operator", selections={})
        except (OSError, ValueError, RecursionError):
            raise AgentOperationsFailure("AGENT_SELECTION_UNAVAILABLE") from None

    def selection(self) -> SelectionFile:
        """Return the current durable overrides, or the empty state when unconfigured."""
        return self._selection(self._directory() / "selection.json")

    def update_selection(self, update: Callable[[SelectionFile], SelectionFile]) -> SelectionFile:
        """Recheck state under the cross-process lock and replace the selection atomically."""
        root = self._directory()
        path = root / "selection.json"
        lock = root / ".selection.lock"
        try:
            with suppress(FileNotFoundError):
                _regular_file(lock)
            with FileLock(str(lock), timeout=1):
                current = self._selection(path)
                updated = update(current)
                if current != updated:
                    self._write_selection(path, updated)
                return updated
        except Timeout:
            raise AgentOperationsFailure("AGENT_SELECTION_BUSY") from None
        except OSError:
            raise AgentOperationsFailure("AGENT_SELECTION_UNAVAILABLE") from None

    def _write_selection(self, path: Path, selection: SelectionFile) -> None:
        pending: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".selection-", delete=False) as output:
                pending = Path(output.name)
                output.write(selection.model_dump_json().encode("utf-8") + b"\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(pending, path)
        finally:
            if pending is not None:
                pending.unlink(missing_ok=True)

    def run_ids(self) -> list[str]:
        """List local records with a bounded scan; callers rotate old history."""
        directory = self._history()
        try:
            with os.scandir(directory) as entries:
                candidates = list(islice(entries, _MAX_RUN_FILES + 1))
            if len(candidates) > _MAX_RUN_FILES:
                raise AgentOperationsFailure("AGENT_HISTORY_LIMIT")
            return [Path(entry.name).stem for entry in candidates if entry.name.endswith(".jsonl")]
        except OSError:
            raise AgentOperationsFailure("AGENT_HISTORY_UNAVAILABLE") from None

    def events(self, run_id: str) -> tuple[AgentEvent, ...]:
        """Read one trusted run, quarantine unsafe or conflicting records, and ignore partial tails."""
        directory = self._history()
        try:
            path = directory / f"{_RUN_ID.validate_python(run_id, strict=True)}.jsonl"
            file_info = _regular_file(path)
            return self._events(path, file_info, file_info.st_mtime_ns)
        except FileNotFoundError:
            raise AgentOperationsFailure("AGENT_RUN_NOT_FOUND", 404) from None
        except (OSError, ValueError, RecursionError):
            raise AgentOperationsFailure("AGENT_RUN_UNAVAILABLE") from None
