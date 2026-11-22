"""API composition checks use the neutral persistence port without database SDKs."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.workbench.api.application import create_app
from apps.workbench.api.config import ApiSettings
from apps.workbench.api.persistence import DatabaseUnavailable, PersistenceError, SchemaIncompatible, WorkspaceNotFound
from apps.workbench.api.tests._persistence import _DatabaseProbe


def test_database_readiness_does_not_enable_execution_profiles() -> None:
    """A healthy storage port proves persistence only, not an implemented search endpoint."""
    database = _DatabaseProbe()
    with TestClient(
        create_app(settings=ApiSettings(), persistence=database), base_url="http://127.0.0.1:8011"
    ) as client:
        assert database.started == 1
        assert client.get("/api/v1/health/live").status_code == 200
        assert client.get("/api/v1/health/ready").status_code == 503
        capabilities = client.get("/api/v1/capabilities").json()
        assert capabilities["dependencies"]["database"] == {
            "status": "ready",
            "schema_revision": "0001",
            "workspace_id": "development",
            "source_count": 8,
            "chunk_count": 8,
        }
        assert capabilities["profiles"] == []
        assert capabilities["features"] == {
            "search": False,
            "documents": False,
            "upload": False,
            "document_details": False,
            "jobs": False,
        }
    assert database.closed == 1


@pytest.mark.parametrize(
    ("failure", "state"),
    [
        (DatabaseUnavailable("private-dsn-sentinel"), "unavailable"),
        (SchemaIncompatible("private-dsn-sentinel"), "incompatible"),
        (WorkspaceNotFound("private-dsn-sentinel"), "empty"),
    ],
)
def test_unhealthy_storage_is_reported_without_private_diagnostics(failure: PersistenceError, state: str) -> None:
    """Database state never converts liveness into readiness or exposes connector errors."""
    database = _DatabaseProbe()
    database.failure = failure
    with TestClient(
        create_app(settings=ApiSettings(), persistence=database), base_url="http://127.0.0.1:8011"
    ) as client:
        assert client.get("/api/v1/health/live").status_code == 200
        assert client.get("/api/v1/health/ready").status_code == 503
        response = client.get("/api/v1/capabilities")
        assert response.json()["dependencies"]["database"]["status"] == state
        assert response.json()["profiles"] == []
        assert "private-dsn-sentinel" not in response.text
    assert database.closed == 1


def test_database_connection_secret_is_redacted_from_configuration() -> None:
    """Secret settings retain the URI only at the infrastructure composition edge."""
    secret = "test-password-sentinel"
    settings = ApiSettings.from_env(
        {"WORKBENCH_DB_DSN": f"postgresql://workbench_app:{secret}@127.0.0.1:55432/workbench"}
    )
    assert settings.database_dsn is not None
    assert secret in settings.database_dsn.get_secret_value()
    assert secret not in repr(settings) + settings.model_dump_json()
    with pytest.raises(ValidationError) as failure:
        ApiSettings.from_env({"WORKBENCH_DB_DSN": f"postgresql://workbench_app:{secret}@remote.example/workbench"})
    assert secret not in str(failure.value)
