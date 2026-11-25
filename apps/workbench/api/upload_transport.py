"""Strict, in-memory multipart decoding inside the separately bounded upload route."""

import re
from dataclasses import dataclass
from email.headerregistry import BaseHeader
from email.message import EmailMessage
from email.policy import default

from pydantic import ValidationError
from python_multipart import MultipartParser
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header
from starlette.requests import Request

from apps.workbench.contracts.schemas import UploadLocation
from apps.workbench.ingestion.upload_policy import upload_file_byte_limit

_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}")
_IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9_-]{8,128}")
_FIELDS = frozenset({"file", "source_id", "expected_active_version_id", "upload_location"})
_FILENAME = b"filename"
_BACKSLASH = b"\\"
_FORM_DATA = b"form-data"
_FIELD_NAME = b"name"
_MULTIPART_TYPE = b"multipart/form-data"


def _validate_parameters(name: str, value: str) -> None:
    try:
        message = EmailMessage(policy=default)
        message[name] = value
        header = message[name]
        invalid = not isinstance(header, BaseHeader) or bool(header.defects)
    except (ValueError, TypeError):
        invalid = True
    if invalid:
        raise UploadTransportError()


class UploadTransportError(ValueError):
    """A safe framing refusal, never a parser diagnostic containing source bytes."""

    def __init__(self, *, status: int = 400, code: str = "INVALID_REQUEST") -> None:
        self.status = status
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class UploadParts:
    content: bytes
    filename: str
    declared_mime: str | None
    idempotency_key: str
    source_id: str | None
    expected_active_version_id: str | None
    upload_location: UploadLocation | None = None


class _MultipartUpload:
    def __init__(self) -> None:
        self.parts: dict[str, bytes] = {}
        self.filename: str | None = None
        self.mime: str | None = None
        self.finished = False
        self._headers: dict[bytes, bytes] = {}
        self._header_name = bytearray()
        self._header_value = bytearray()
        self._part = bytearray()
        self._name = ""
        self._part_count = 0
        self._headers_size = 0

    def on_part_begin(self) -> None:
        self._part_count += 1
        if self._part_count > len(_FIELDS):
            raise UploadTransportError()
        self._headers = {}
        self._part = bytearray()
        self._name = ""
        self._headers_size = 0

    def _header_data(self, data: bytes, start: int, end: int, target: bytearray) -> None:
        self._headers_size += end - start
        if self._headers_size > 8192:
            raise UploadTransportError()
        target.extend(data[start:end])

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._header_data(data, start, end, self._header_name)

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._header_data(data, start, end, self._header_value)

    def on_header_end(self) -> None:
        name = bytes(self._header_name).lower()
        if name in self._headers or name not in {b"content-disposition", b"content-type"}:
            raise UploadTransportError()
        self._headers[name] = bytes(self._header_value)
        self._header_name.clear()
        self._header_value.clear()

    def on_headers_finished(self) -> None:
        raw_disposition = self._headers.get(b"content-disposition", b"")
        # The multipart library normalizes legacy Windows paths; reject them before that loses the evidence.
        if _FILENAME in raw_disposition.lower() and _BACKSLASH in raw_disposition:
            raise UploadTransportError()
        _validate_parameters("Content-Disposition", raw_disposition.decode("latin-1"))
        disposition, options = parse_options_header(raw_disposition)
        if disposition != _FORM_DATA or _FIELD_NAME not in options:
            raise UploadTransportError()
        try:
            self._name = options[b"name"].decode("ascii")
            if self._name not in _FIELDS or self._name in self.parts:
                raise UploadTransportError()
            if self._name == "file":
                self.filename = options[b"filename"].decode("utf-8")
                mime = self._headers.get(b"content-type")
                self.mime = mime.decode("ascii") if mime else None
            elif _FILENAME in options:
                raise UploadTransportError()
        except (KeyError, UnicodeError):
            raise UploadTransportError() from None

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        limit = (
            upload_file_byte_limit(filename=self.filename or "", declared_mime=self.mime)
            if self._name == "file"
            else 8192
            if self._name == "upload_location"
            else 128
        )
        if len(self._part) + end - start > limit:
            raise UploadTransportError(status=413, code="PAYLOAD_TOO_LARGE")
        self._part.extend(data[start:end])

    def on_part_end(self) -> None:
        self.parts[self._name] = bytes(self._part)

    def on_end(self) -> None:
        self.finished = True


async def read_upload(request: Request) -> UploadParts:
    """Decode one file and optional guarded-update fields; the ASGI boundary owns total bytes/deadline."""
    keys = request.headers.getlist("idempotency-key")
    if len(keys) != 1 or _IDEMPOTENCY_KEY.fullmatch(keys[0]) is None:
        raise UploadTransportError()
    content_type = request.headers.get("content-type", "")
    _validate_parameters("Content-Type", content_type)
    kind, options = parse_options_header(content_type)
    boundary = options.get(b"boundary", b"")
    if kind != _MULTIPART_TYPE or not 1 <= len(boundary) <= 200 or any(byte < 33 or byte > 126 for byte in boundary):
        raise UploadTransportError()
    form = _MultipartUpload()
    try:
        parser = MultipartParser(
            boundary,
            callbacks={
                "on_part_begin": form.on_part_begin,
                "on_part_data": form.on_part_data,
                "on_part_end": form.on_part_end,
                "on_header_field": form.on_header_field,
                "on_header_value": form.on_header_value,
                "on_header_end": form.on_header_end,
                "on_headers_finished": form.on_headers_finished,
                "on_end": form.on_end,
            },
        )
        parser.write(await request.body())
        parser.finalize()
    except (MultipartParseError, ValueError) as error:
        if isinstance(error, UploadTransportError):
            raise
        raise UploadTransportError() from None
    if not form.finished or "file" not in form.parts or not form.filename:
        raise UploadTransportError()
    fields: dict[str, str] = {}
    for name in ("source_id", "expected_active_version_id"):
        if name in form.parts:
            try:
                value = form.parts[name].decode("ascii")
            except UnicodeError:
                raise UploadTransportError() from None
            if _IDENTIFIER.fullmatch(value) is None:
                raise UploadTransportError()
            fields[name] = value
    if ("source_id" in fields) != ("expected_active_version_id" in fields):
        raise UploadTransportError()
    try:
        location = (
            UploadLocation.model_validate_json(form.parts["upload_location"])
            if "upload_location" in form.parts
            else None
        )
    except ValidationError:
        raise UploadTransportError() from None
    return UploadParts(
        content=form.parts["file"],
        filename=form.filename,
        declared_mime=form.mime,
        idempotency_key=keys[0],
        source_id=fields.get("source_id"),
        expected_active_version_id=fields.get("expected_active_version_id"),
        upload_location=location,
    )
