"""Fixed transport ceilings for the qualified synchronous upload path."""

from apps.workbench.api.parser_registry import UploadLimits
from apps.workbench.api.pdf_models import PdfLimits


def pdf_upload_candidate(filename: str, declared_mime: str | None, content: bytes | None = None) -> bool:
    """A resource-admission hint only; the parser still verifies the complete PDF independently."""
    return (
        isinstance(filename, str)
        and filename.lower().endswith(".pdf")
        and (
            declared_mime is None
            or isinstance(declared_mime, str)
            and declared_mime.split(";", 1)[0].strip().lower() == "application/pdf"
        )
        and (content is None or content.startswith(b"%PDF-"))
    )


def upload_file_byte_limit(*, filename: str = "", declared_mime: str | None = None) -> int:
    """Reuse the parser's original-byte ceiling; HTTP framing has its own allowance."""
    return PdfLimits().max_bytes if pdf_upload_candidate(filename, declared_mime) else UploadLimits().max_bytes


def upload_request_byte_limit() -> int:
    """Bound the file plus multipart headers, boundary markers and update fields."""
    return PdfLimits().max_bytes + 65_536
