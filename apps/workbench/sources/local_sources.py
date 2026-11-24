"""Resolve registered originals inside a trusted local root and select them in Explorer."""

import asyncio
import ctypes
import hashlib
import os
import re
import stat
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path, PurePosixPath
from typing import Protocol

from apps.workbench.contracts.schemas import LocalSourceFileResponse, Meta
from apps.workbench.persistence.models import (
    LocalOriginalRecord,
    LocalOriginalRegistration,
    PersistencePort,
    WorkspaceContext,
)

_MAX_ORIGINAL_BYTES = 512 * 1024 * 1024
_HASH_TIMEOUT_SECONDS = 5.0


class SourceNotFound(Exception):
    pass


class SourceFileUnavailable(Exception):
    pass


class FileRevealFailed(Exception):
    pass


class LocalFileLauncher(Protocol):
    def available(self) -> bool:
        """Report whether this host can dispatch a desktop selection."""
        ...

    def reveal(self, path: Path) -> None:
        """Dispatch native file selection without executing the file."""
        ...


def _safe_parts(parts: tuple[str, ...]) -> bool:
    return all(
        part not in {"", ".", ".."}
        and not part.endswith((" ", "."))
        and not re.search(r'[\x00-\x1f\x7f:<>"|?*\\]', part)
        and not re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part, flags=re.IGNORECASE)
        for part in parts
    )


def _local_drive(root: Path) -> bool:
    if sys.platform != "win32":
        return True
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    drive_type = kernel.GetDriveTypeW
    drive_type.argtypes = [ctypes.c_wchar_p]
    drive_type.restype = ctypes.c_uint
    return drive_type(root.anchor) in {2, 3}


def _regular_file(root: Path, path: Path) -> Path:
    if not root.is_absolute() or not path.is_absolute() or str(root).startswith(("\\\\", "//")):
        raise SourceFileUnavailable
    if not _local_drive(root):
        raise SourceFileUnavailable
    try:
        relative = path.relative_to(root)
        if not _safe_parts(relative.parts) or not relative.parts:
            raise SourceFileUnavailable
        # Refuse reparse points even when they presently resolve inside the root.
        for candidate in [
            *reversed(root.parents),
            root,
            *[root.joinpath(*relative.parts[:index]) for index in range(1, len(relative.parts) + 1)],
        ]:
            properties = candidate.lstat()
            if stat.S_ISLNK(properties.st_mode) or getattr(properties, "st_file_attributes", 0) & 0x400:
                raise SourceFileUnavailable
        resolved_root = root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        properties = resolved.stat()
        if (
            not resolved.is_relative_to(resolved_root)
            or not stat.S_ISREG(properties.st_mode)
            or properties.st_size > _MAX_ORIGINAL_BYTES
        ):
            raise SourceFileUnavailable
        return resolved
    except (OSError, RuntimeError, ValueError):
        raise SourceFileUnavailable from None


def _file_hash(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if before.st_size > _MAX_ORIGINAL_BYTES:
                raise SourceFileUnavailable
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
            after = os.fstat(stream.fileno())
        if (before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns) != (
            after.st_ino,
            after.st_dev,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise SourceFileUnavailable
        return digest
    except OSError:
        raise SourceFileUnavailable from None


def _file_identity(path: Path) -> tuple[int, int, int, int]:
    try:
        current = path.stat()
    except OSError:
        raise SourceFileUnavailable from None
    return current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns


def inspect_local_original(root: Path, path: Path) -> LocalOriginalRegistration:
    """Validate a trusted operator's existing file and record its byte fingerprint."""
    resolved = _regular_file(root, path)
    relative_path = resolved.relative_to(root.resolve(strict=True)).as_posix()
    return LocalOriginalRegistration(relative_path=relative_path, sha256=_file_hash(resolved))


class WindowsExplorer:
    def available(self) -> bool:
        """Require a Windows user session with access to the current input desktop."""
        if sys.platform != "win32":
            return False
        try:
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            session_id = ctypes.c_uint()
            get_session = kernel.ProcessIdToSessionId
            get_session.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_uint)]
            get_session.restype = ctypes.c_int
            if not get_session(os.getpid(), ctypes.byref(session_id)) or not session_id.value:
                return False
            user = ctypes.WinDLL("user32", use_last_error=True)
            desktop = user.OpenInputDesktop
            desktop.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_uint]
            desktop.restype = ctypes.c_void_p
            handle = desktop(0, False, 0x0100)
            if not handle:
                return False
            close = user.CloseDesktop
            close.argtypes = [ctypes.c_void_p]
            close.restype = ctypes.c_int
            return bool(close(handle))
        except (OSError, AttributeError):
            return False

    def reveal(self, path: Path) -> None:
        """Use a full-file PIDL with cidl=0 to select the item in its parent folder."""
        if not self.available():
            raise FileRevealFailed
        ole = ctypes.WinDLL("ole32", use_last_error=True)
        shell = ctypes.WinDLL("shell32", use_last_error=True)
        initialize = ole.CoInitializeEx
        initialize.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        initialize.restype = ctypes.c_long
        uninitialize = ole.CoUninitialize
        uninitialize.argtypes = []
        uninitialize.restype = None
        create = shell.ILCreateFromPathW
        create.argtypes = [ctypes.c_wchar_p]
        create.restype = ctypes.c_void_p
        select = shell.SHOpenFolderAndSelectItems
        select.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        select.restype = ctypes.c_long
        free = ole.CoTaskMemFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = None
        initialized = initialize(None, 2)
        if initialized < 0:
            raise FileRevealFailed
        try:
            item = create(str(path))
            if not item:
                raise FileRevealFailed
            try:
                if select(item, 0, None, 0) < 0:
                    raise FileRevealFailed
            finally:
                free(item)
        finally:
            uninitialize()


class LocalSources:
    def __init__(self, *, persistence: PersistencePort | None, root: str | None, launcher: LocalFileLauncher) -> None:
        self.persistence = persistence
        self.root = Path(root) if root is not None else None
        self.launcher = launcher

    async def _record(self, context: WorkspaceContext, *, source_id: str, version_id: str) -> LocalOriginalRecord:
        if self.persistence is None:
            raise SourceNotFound
        record = await self.persistence.get_local_original(context, source_id=source_id, version_id=version_id)
        if record is None or record.source_id != source_id or record.version_id != version_id:
            raise SourceNotFound
        return record

    def _path(self, record: LocalOriginalRecord) -> Path:
        if self.root is None or record.is_demo or record.registration is None:
            raise SourceFileUnavailable
        relative = PurePosixPath(record.registration.relative_path)
        if relative.is_absolute() or not _safe_parts(relative.parts):
            raise SourceFileUnavailable
        return _regular_file(self.root, self.root.joinpath(*relative.parts))

    async def describe(
        self, context: WorkspaceContext, *, source_id: str, version_id: str, meta: Meta
    ) -> LocalSourceFileResponse:
        """Return only a display basename and a non-authoritative availability hint."""
        record = await self._record(context, source_id=source_id, version_id=version_id)
        response = LocalSourceFileResponse(**meta.model_dump(), name=None, can_reveal=False)
        if record.is_demo:
            return response.model_copy(update={"reason": "demo_source"})
        if record.registration is None:
            return response.model_copy(update={"reason": "not_registered"})
        name = PurePosixPath(record.registration.relative_path).name
        if not name or len(name) > 255 or not _safe_parts((name,)):
            return response.model_copy(update={"reason": "file_unavailable"})
        response = response.model_copy(update={"name": name})
        if self.root is None:
            return response.model_copy(update={"reason": "root_unconfigured"})
        try:
            await asyncio.to_thread(self._path, record)
        except SourceFileUnavailable:
            return response.model_copy(update={"reason": "file_unavailable"})
        if not await asyncio.to_thread(self.launcher.available):
            return response.model_copy(update={"reason": "host_unavailable"})
        return response.model_copy(update={"can_reveal": True})

    async def reveal(
        self,
        context: WorkspaceContext,
        *,
        source_id: str,
        version_id: str,
        before_dispatch: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """Recheck active provenance and original bytes before native dispatch."""
        record = await self._record(context, source_id=source_id, version_id=version_id)
        path = await asyncio.to_thread(self._path, record)
        if record.registration is None or not await asyncio.to_thread(self.launcher.available):
            raise SourceFileUnavailable
        identity = await asyncio.to_thread(_file_identity, path)
        try:
            async with asyncio.timeout(_HASH_TIMEOUT_SECONDS):
                digest = await asyncio.to_thread(_file_hash, path)
        except TimeoutError:
            raise SourceFileUnavailable from None
        if digest != record.registration.sha256:
            raise SourceFileUnavailable
        current = await self._record(context, source_id=source_id, version_id=version_id)
        if current != record:
            raise SourceFileUnavailable
        verified = await asyncio.to_thread(self._path, current)
        if await asyncio.to_thread(_file_identity, verified) != identity:
            raise SourceFileUnavailable
        if before_dispatch is not None:
            await before_dispatch()
        await asyncio.sleep(0)
        try:
            await asyncio.to_thread(self.launcher.reveal, verified)
        except SourceFileUnavailable:
            raise
        except Exception:
            raise FileRevealFailed from None
