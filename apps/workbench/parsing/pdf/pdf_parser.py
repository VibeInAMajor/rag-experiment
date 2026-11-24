"""Owned, quota-limited Docling subprocess with bounded data-only input/output."""

import os
import subprocess
import sys
import sysconfig
from pathlib import Path
from threading import BoundedSemaphore

from apps.workbench.parsing.parser_registry import ParseErrorCode, ParsingError
from apps.workbench.parsing.pdf.pdf_assets import pdf_assets_directory, pdf_runtime_available
from apps.workbench.parsing.pdf.pdf_models import PdfDocument, PdfLimits
from apps.workbench.parsing.pdf.pdf_sandbox import PdfProcessBudget

_PARSER_SLOT = BoundedSemaphore(1)
_ROOT = Path(__file__).resolve().parents[4]
_MAX_RESULT_BYTES = 8_388_608


def _worker_command(limits: PdfLimits) -> list[str]:
    # Windows venv launchers spawn an uncontained descendant. Start the base interpreter
    # directly and inject only the reviewed Hatch site-packages and repository roots.
    bootstrap = (
        "import runpy,sys;sys.path[:0]=sys.argv[1:3];sys.argv=sys.argv[3:];"
        "runpy.run_module('apps.workbench.parsing.pdf.pdf_worker',run_name='__main__')"
    )
    return [
        getattr(sys, "_base_executable", sys.executable),
        "-S",
        "-c",
        bootstrap,
        sysconfig.get_paths()["purelib"],
        str(_ROOT),
        "pdf-worker",
        str(pdf_assets_directory()),
        limits.model_dump_json(),
    ]


def _worker_environment() -> dict[str, str]:
    retained = {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "USERPROFILE", "HOMEDRIVE", "HOMEPATH"}
    environment = {key: value for key, value in os.environ.items() if key.upper() in retained}
    environment.update(
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        DO_NOT_TRACK="1",
        TOKENIZERS_PARALLELISM="false",
        OMP_NUM_THREADS="4",
        HAYSTACK_TELEMETRY_ENABLED="false",
        HAYSTACK_CONTENT_TRACING_ENABLED="false",
    )
    return environment


def _decode_result(output: bytes, returncode: int | None) -> PdfDocument:
    if returncode != 0 or len(output) > _MAX_RESULT_BYTES:
        raise ParsingError(ParseErrorCode.PDF_RESOURCE_LIMIT)
    if output.startswith(b"ERROR:"):
        try:
            code = ParseErrorCode(output[6:].decode("ascii"))
        except (ValueError, UnicodeError):
            code = ParseErrorCode.PDF_CORRUPT
        raise ParsingError(code)
    return PdfDocument.model_validate_json(output)


def extract_pdf(content: bytes, *, limits: PdfLimits = PdfLimits()) -> PdfDocument:
    """Run installed Docling offline; timeout, crash and quota failures produce no partial result."""
    if not isinstance(content, bytes) or len(content) > limits.max_bytes:
        raise ParsingError(ParseErrorCode.PDF_TOO_LARGE)
    if not pdf_runtime_available():
        raise ParsingError(ParseErrorCode.PARSER_UNAVAILABLE, reason="PDF_RUNTIME_UNAVAILABLE")
    if not _PARSER_SLOT.acquire(blocking=False):
        raise ParsingError(ParseErrorCode.PDF_BUSY)
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            _worker_command(limits),
            cwd=_ROOT,
            env=_worker_environment(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        with PdfProcessBudget(process.pid, limits=limits):
            output, _ = process.communicate(input=content, timeout=limits.wall_seconds)
            return _decode_result(output, process.returncode)
    except subprocess.TimeoutExpired:
        raise ParsingError(ParseErrorCode.PDF_PARSE_TIMEOUT) from None
    except ParsingError:
        raise
    except Exception:
        raise ParsingError(ParseErrorCode.PARSER_UNAVAILABLE, reason="PDF_WORKER_UNAVAILABLE") from None
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        _PARSER_SLOT.release()
