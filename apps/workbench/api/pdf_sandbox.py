"""OS resource quotas for the owned PDF child process; no caller-provided commands."""

import ctypes
import os
from contextlib import AbstractContextManager
from ctypes import wintypes
from typing import Any

from apps.workbench.api.pdf_models import PdfLimits


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_longlong),
        ("job_time", ctypes.c_longlong),
        ("flags", wintypes.DWORD),
        ("minimum_working_set", ctypes.c_size_t),
        ("maximum_working_set", ctypes.c_size_t),
        ("active_processes", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority", wintypes.DWORD),
        ("scheduling", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_ulonglong)
        for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", _BasicLimits),
        ("io", _IoCounters),
        ("process_memory", ctypes.c_size_t),
        ("job_memory", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t),
        ("peak_job_memory", ctypes.c_size_t),
    ]


def _require_sandbox(failed: bool) -> None:
    if failed:
        raise RuntimeError("PDF_SANDBOX_UNAVAILABLE")


class PdfProcessBudget(AbstractContextManager["PdfProcessBudget"]):
    """Attach the already-owned child before supplying source bytes; closing its job kills descendants."""

    def __init__(self, process_id: int, *, limits: PdfLimits) -> None:
        self._process_id = process_id
        self._limits = limits
        self._kernel: Any = None
        self._job: Any = None

    def __enter__(self) -> "PdfProcessBudget":
        if os.name != "nt":
            # The POSIX worker installs resource limits itself before importing parser libraries.
            return self
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
        kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            raise RuntimeError("PDF_SANDBOX_UNAVAILABLE")
        self._kernel, self._job = kernel, job
        settings = _ExtendedLimits()
        settings.basic.flags = 0x00000002 | 0x00000008 | 0x00000100 | 0x00002000
        settings.basic.process_time = self._limits.cpu_seconds * 10_000_000
        settings.basic.active_processes = 1
        settings.process_memory = self._limits.memory_bytes
        handle = kernel.OpenProcess(0x00000001 | 0x00000100 | 0x00000200 | 0x00100000, False, self._process_id)
        try:
            _require_sandbox(
                not handle
                or not kernel.SetInformationJobObject(job, 9, ctypes.byref(settings), ctypes.sizeof(settings))
                or not kernel.AssignProcessToJobObject(job, handle)
            )
        except BaseException:
            kernel.CloseHandle(job)
            self._job = None
            raise
        finally:
            if handle:
                kernel.CloseHandle(handle)
        return self

    def __exit__(self, *_args: object) -> None:
        if self._kernel is not None and self._job is not None:
            self._kernel.CloseHandle(self._job)
            self._job = None
