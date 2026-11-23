"""Local-only configuration contracts, independent of provider configuration."""

from typing import Any

import pytest
from pydantic import ValidationError

from apps.workbench.api.config import ApiSettings


def test_defaults_are_loopback_with_explicit_browser_origins() -> None:
    """Default startup cannot expose the bootstrap on a public interface."""
    settings = ApiSettings.from_env({})
    assert settings.host == "127.0.0.1"
    assert settings.port == 8011
    assert set(settings.allowed_origins) == {
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    }


def test_environment_parsing_is_explicit_and_does_not_force_readiness() -> None:
    """Only deployment settings may be controlled by environment variables."""
    settings = ApiSettings.from_env(
        {
            "WORKBENCH_API_HOST": "::1",
            "WORKBENCH_API_PORT": "8020",
            "WORKBENCH_API_BACKEND_REVISION": "local-api-revision",
            "WORKBENCH_API_ALLOWED_ORIGINS": "http://localhost:5173,http://127.0.0.1:4173",
            "WORKBENCH_API_READY": "true",
            "OPENAI_API_KEY": "unused-provider-secret",
        }
    )
    assert settings.host == "::1"
    assert settings.port == 8020
    assert settings.backend_revision == "local-api-revision"
    assert settings.allowed_origins == ("http://localhost:5173", "http://127.0.0.1:4173")
    assert "unused-provider-secret" not in settings.model_dump_json()
    assert "ready" not in ApiSettings.model_fields


@pytest.mark.parametrize("port", [0, -1, 65536, True, "8011", 8011.5])
def test_port_rejects_invalid_or_coerced_values(port: Any) -> None:
    """Configuration accepts only an actual in-range integer port."""
    with pytest.raises(ValidationError):
        ApiSettings(port=port)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "example.com", "127.0.0.2", "localhost.attacker.example"])
def test_listener_host_must_be_loopback(host: str) -> None:
    """A typo cannot quietly change the local-development security boundary."""
    with pytest.raises(ValidationError):
        ApiSettings.model_validate({"host": host})


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "null",
        "https://remote.example",
        "http://localhost.attacker.example:5173",
        "http://user:secret@localhost:5173",
        "http://localhost:5173/path",
        "http://localhost:5173?secret=value",
        "http://localhost:5173#fragment",
        "ftp://localhost:5173",
    ],
)
def test_browser_origins_require_bare_local_http_origins(origin: str) -> None:
    """Reject wildcard, credential-bearing and ambiguous origin settings."""
    with pytest.raises(ValidationError):
        ApiSettings(allowed_origins=(origin,))


@pytest.mark.parametrize("value", ["", "not-a-port", "65536", "2.5", " true "])
def test_invalid_environment_port_fails_startup(value: str) -> None:
    """Malformed environment values cannot silently fall back to defaults."""
    with pytest.raises((ValidationError, ValueError)):
        ApiSettings.from_env({"WORKBENCH_API_PORT": value})


def test_unknown_application_fields_are_rejected() -> None:
    """There is no undocumented ready flag or provider configuration escape hatch."""
    with pytest.raises(ValidationError):
        ApiSettings.model_validate({"ready": True})


def test_legacy_snapshot_requires_explicit_operator_selection() -> None:
    """Default startup never silently selects the full-corpus rollback scan."""
    assert ApiSettings.from_env({}).corpus_snapshot_mode == "persisted"
    settings = ApiSettings.from_env({"WORKBENCH_CORPUS_SNAPSHOT_MODE": "legacy"})
    assert settings.corpus_snapshot_mode == "legacy"
    with pytest.raises(ValidationError):
        ApiSettings.from_env({"WORKBENCH_CORPUS_SNAPSHOT_MODE": "automatic"})


@pytest.mark.parametrize("revision", ["", "with spaces", "secret=value", "r" * 129])
def test_backend_revision_is_a_bounded_opaque_identifier(revision: str) -> None:
    """Configuration cannot inject arbitrary text into every response and log correlation."""
    with pytest.raises(ValidationError):
        ApiSettings(backend_revision=revision)
