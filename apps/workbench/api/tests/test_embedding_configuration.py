"""Local embedding configuration is bounded, opt-in and incapable of claiming qualification."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from apps.workbench.api.config import ApiSettings
from apps.workbench.api.embedding_config import (
    EmbeddingConfigurationError,
    EmbeddingSettings,
    load_embedding_settings,
    validate_embedding_settings_yaml,
)


def _configuration(**changes: Any) -> str:
    profile = {
        "profile_id": "local-qwen",
        "profile_revision": "local-qwen-r1",
        "provider_adapter_id": "tei-openai",
        "model_id": "Qwen/Qwen3-Embedding-4B",
        "model_revision": "a" * 40,
        "model_digest": "b" * 64,
        "tokenizer_digest": "c" * 64,
        "tokenizer_revision": "pinned-counter-r1",
        "dimensions": 2560,
    }
    return yaml.safe_dump({"embedding": {"mode": "qualification_only", "profile": profile, **changes}})


def test_defaults_do_not_claim_or_enable_embedding_execution() -> None:
    """Shipping placeholders cannot advertise a model profile or start a transport."""
    settings = load_embedding_settings({})
    assert settings == EmbeddingSettings()
    assert settings.mode == "disabled" and settings.profile is None
    assert settings.endpoint == "http://127.0.0.1:8082"
    assert ApiSettings.from_env({}).embedding == settings
    assert "ready" not in settings.model_dump()


def test_manual_qualification_requires_complete_profile_pin(tmp_path: Path) -> None:
    """A versioned pin is parsed without becoming runtime evidence or an executable search profile."""
    path = tmp_path / "local_embedding.yaml"
    path.write_text(_configuration(endpoint="http://[::1]:8082/"), encoding="utf-8")
    settings = load_embedding_settings({"WORKBENCH_EMBEDDING_CONFIG": str(path)})
    assert settings.mode == "qualification_only" and settings.profile is not None
    assert settings.profile.dimensions == 2560
    assert settings.profile.profile_revision == "local-qwen-r1"
    assert settings.endpoint == "http://[::1]:8082"
    assert ApiSettings.from_env({"WORKBENCH_EMBEDDING_CONFIG": str(path)}).embedding == settings


@pytest.mark.parametrize(
    "content",
    [
        "",
        "embedding: null",
        "embedding: {mode: qualification_only}",
        "embedding: {mode: enabled}",
        "embedding: {mode: disabled, mode: qualification_only}",
        "embedding: &settings {mode: disabled}",
        "embedding: {mode: disabled, profile: *settings}",
        "embedding: {enabled: true}",
        "embedding: {ready: true}",
        "embedding: {provider_sdk: arbitrary.module}",
        "embedding: {endpoint: https://remote.example}",
        "embedding: {endpoint: 'http://u:secret@127.0.0.1:8081'}",
        "embedding: {endpoint: 'http://127.0.0.1:0'}",
        "embedding: {endpoint: 'http://127.0.0.1:8081/private'}",
        "embedding: {endpoint: 'http://127.0.0.1:8081?secret=value'}",
        "embedding: {endpoint: 'http://localhost:8081'}",
        "embedding: {profile: {model_digest: placeholder}}",
        "embedding: {profile: !!python/object:arbitrary.Class {}}",
        "embedding: {}\nother: value",
        "embedding: {}\n---\nembedding: {}",
        "embedding: " + "[" * 14 + "0" + "]" * 14,
        "embedding: {}\n#" + "x" * 65_536,
    ],
)
def test_invalid_configuration_has_one_safe_error(content: str) -> None:
    """Aliases, duplicate keys, unknown modes, incomplete pins and external endpoints fail closed."""
    with pytest.raises(EmbeddingConfigurationError) as error:
        validate_embedding_settings_yaml(content)
    assert str(error.value) == "INVALID_EMBEDDING_CONFIGURATION"


@pytest.mark.parametrize(
    "path",
    [
        "",
        "https://remote.example/config.yaml",
        "\\\\server\\share\\config.yaml",
        "//server/share/config.yaml",
        "invalid\npath",
    ],
)
def test_configuration_path_is_local_and_explicit(path: str) -> None:
    """A configuration override cannot fetch remote content or expose submitted paths in errors."""
    with pytest.raises(EmbeddingConfigurationError) as error:
        load_embedding_settings({"WORKBENCH_EMBEDDING_CONFIG": path})
    assert str(error.value) == "INVALID_EMBEDDING_CONFIGURATION"


def test_unreadable_nonunicode_and_oversized_files_are_safe(tmp_path: Path) -> None:
    """Missing or malformed files never silently activate or fall back to another profile."""
    path = tmp_path / "private-config.yaml"
    with pytest.raises(EmbeddingConfigurationError):
        load_embedding_settings({"WORKBENCH_EMBEDDING_CONFIG": str(path)})
    for content in (b"\xff", b"x" * 65_537):
        path.write_bytes(content)
        with pytest.raises(EmbeddingConfigurationError):
            load_embedding_settings({"WORKBENCH_EMBEDDING_CONFIG": str(path)})


def test_direct_settings_are_strict_and_immutable() -> None:
    """Programmatic configuration obeys the same constraints without coercing an enabled flag."""
    with pytest.raises(ValidationError):
        EmbeddingSettings(mode="qualification_only")
    with pytest.raises(ValidationError):
        EmbeddingSettings.model_validate({"mode": True})
    settings = EmbeddingSettings()
    with pytest.raises(ValidationError):
        settings.mode = "qualification_only"
