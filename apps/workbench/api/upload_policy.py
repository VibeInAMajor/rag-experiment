"""Fixed transport ceilings for the qualified synchronous upload path."""

from apps.workbench.api.parser_registry import UploadLimits


def upload_file_byte_limit() -> int:
    """Reuse the parser's original-byte ceiling; HTTP framing has its own allowance."""
    return UploadLimits().max_bytes


def upload_request_byte_limit() -> int:
    """Bound the file plus multipart headers, boundary markers and update fields."""
    return upload_file_byte_limit() + 65_536
