"""Disabled-by-default local embedding configuration without capability or runtime attestation claims."""

from collections.abc import Mapping
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from yaml.events import AliasEvent

from apps.workbench.configuration.document_processing import _yaml_value
from apps.workbench.embedding.embedding import EmbeddingProfile

_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CONFIGURATION = _ROOT / "apps" / "workbench" / "embedding_profiles.yaml"
_MAX_CONFIGURATION_BYTES = 65_536


class EmbeddingConfigurationError(ValueError):
    """Reject operator configuration without exposing paths, fingerprints or submitted input."""

    def __init__(self) -> None:
        super().__init__("INVALID_EMBEDDING_CONFIGURATION")


def validate_embedding_endpoint(endpoint: str) -> str:
    """Require an explicit HTTP loopback IP/port without credentials or path routing."""
    if not isinstance(endpoint, str):
        raise EmbeddingConfigurationError
    try:
        parsed = urlsplit(endpoint)
        valid = (
            parsed.scheme == "http"
            and parsed.hostname in {"127.0.0.1", "::1"}
            and parsed.port is not None
            and 1 <= parsed.port <= 65535
            and parsed.username is None
            and parsed.password is None
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
            and endpoint.isascii()
            and not any(character.isspace() for character in endpoint)
        )
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise EmbeddingConfigurationError
    return endpoint.rstrip("/")


class EmbeddingSettings(BaseModel):
    """Only a manual qualification mode is configurable; inference remains explicitly composed."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)

    mode: Literal["disabled", "qualification_only"] = "disabled"
    endpoint: str = Field(default="http://127.0.0.1:8082", max_length=256, repr=False)
    profile: EmbeddingProfile | None = Field(default=None, repr=False)

    @field_validator("endpoint")
    @classmethod
    def _local_endpoint(cls, value: str) -> str:
        return validate_embedding_endpoint(value)

    @model_validator(mode="after")
    def _qualification_profile(self) -> "EmbeddingSettings":
        if self.mode == "qualification_only" and self.profile is None:
            raise EmbeddingConfigurationError
        if self.profile is not None and self.profile.provider_adapter_id != "tei-openai":
            raise EmbeddingConfigurationError
        return self


def validate_embedding_settings_yaml(content: str) -> EmbeddingSettings:
    """Decode bounded alias-free YAML through the existing duplicate-key-denying node parser."""
    try:
        if len(content.encode("utf-8")) > _MAX_CONFIGURATION_BYTES:
            raise EmbeddingConfigurationError
        if any(
            isinstance(event, AliasEvent) or getattr(event, "anchor", None) is not None for event in yaml.parse(content)
        ):
            raise EmbeddingConfigurationError
        loader = yaml.SafeLoader(content)
        try:
            node = loader.get_single_node()
            if node is None:
                raise EmbeddingConfigurationError
            value = _yaml_value(node, depth=0, remaining=[512], loader=loader)
        finally:
            loader.dispose()
        if not isinstance(value, dict) or set(value) != {"embedding"}:
            raise EmbeddingConfigurationError
        return EmbeddingSettings.model_validate(value["embedding"])
    except (ValueError, UnicodeError, yaml.YAMLError, RecursionError):
        raise EmbeddingConfigurationError from None


def load_embedding_settings(environ: Mapping[str, str]) -> EmbeddingSettings:
    """Read an operator-selected local file; never connect, load weights or advertise readiness."""
    selected = environ.get("WORKBENCH_EMBEDDING_CONFIG")
    try:
        if selected is not None and (
            not selected
            or len(selected) > 2048
            or selected.startswith(("\\\\", "//"))
            or "://" in selected
            or any(ord(character) < 32 for character in selected)
        ):
            raise EmbeddingConfigurationError
        path = _DEFAULT_CONFIGURATION if selected is None else Path(selected)
        if (path.drive or path.root) and not path.is_absolute():
            raise EmbeddingConfigurationError
        path = (path if path.is_absolute() else _ROOT / path).resolve()
        with path.open("rb") as source:
            raw = source.read(_MAX_CONFIGURATION_BYTES + 1)
        if len(raw) > _MAX_CONFIGURATION_BYTES:
            raise EmbeddingConfigurationError
        return validate_embedding_settings_yaml(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise EmbeddingConfigurationError from None
