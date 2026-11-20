"""Validated configuration for the loopback-only development API."""

import os
from collections.abc import Mapping
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.workbench.api.contracts import Identifier


class ApiSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    host: Literal["127.0.0.1", "localhost", "::1"] = "127.0.0.1"
    port: int = Field(default=8011, ge=1, le=65535)
    backend_revision: Identifier = "workbench-api-bootstrap-v1"
    allowed_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    )

    @field_validator("allowed_origins")
    @classmethod
    def _validate_origins(cls, origins: tuple[str, ...]) -> tuple[str, ...]:
        if len(origins) > 16 or len(set(origins)) != len(origins):
            raise ValueError("Origins must be distinct and bounded")
        for origin in origins:
            if not origin.isascii() or any(character.isspace() for character in origin):
                raise ValueError("Origins must be exact ASCII loopback origins")
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("Origins must be exact loopback HTTP origins")
            try:
                port = parsed.port
            except ValueError as exc:
                raise ValueError("Invalid origin port") from exc
            if port is not None and not 1 <= port <= 65535:
                raise ValueError("Invalid origin port")
        return origins

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "ApiSettings":
        """Read only explicit API settings; readiness cannot be configured."""
        environment = os.environ if environ is None else environ
        values: dict[str, object] = {}
        fields = {"HOST": "host", "PORT": "port", "BACKEND_REVISION": "backend_revision"}
        for suffix, field in fields.items():
            value = environment.get(f"WORKBENCH_API_{suffix}")
            if value is not None:
                values[field] = int(value) if suffix == "PORT" else value
        origins = environment.get("WORKBENCH_API_ALLOWED_ORIGINS")
        if origins is not None:
            values["allowed_origins"] = tuple(part.strip() for part in origins.split(","))
        return cls.model_validate(values)
