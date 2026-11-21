"""Trusted CLI admission and registration metadata contract tests."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from apps.workbench.api import source_registration
from apps.workbench.api.persistence import (
    LocalOriginalRecord,
    LocalOriginalRegistration,
    PersistencePort,
    RecordConflict,
    WorkspaceContext,
)


@pytest.mark.parametrize(
    "relative_path",
    ["../secret", "/absolute", "C:/secret", "folder\\secret", "a/../secret", "./file", ".", "file\0name"],
)
def test_registration_model_rejects_non_relative_or_non_normalized_paths(relative_path: str) -> None:
    """Stored locations cannot name a root, traverse parents or carry alternate syntax."""
    with pytest.raises(ValidationError, match="Original location"):
        LocalOriginalRegistration(relative_path=relative_path, sha256="a" * 64)


@pytest.mark.parametrize("digest", ["", "a" * 63, "A" * 64, "g" * 64, "a" * 65])
def test_registration_requires_a_full_normalized_byte_fingerprint(digest: str) -> None:
    """Truncated or malformed byte fingerprints never qualify as registrations."""
    with pytest.raises(ValidationError, match="String should match pattern"):
        LocalOriginalRegistration(relative_path="Original.pdf", sha256=digest)


@pytest.mark.asyncio
@pytest.mark.parametrize("is_demo", [True, None])
async def test_cli_refuses_demo_and_unknown_versions_before_inspecting_any_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, is_demo: bool | None
) -> None:
    """Unknown or synthetic registry entries cannot cause even an operator file read."""
    repository = AsyncMock(spec=PersistencePort)
    repository.get_local_original.return_value = (
        None if is_demo is None else LocalOriginalRecord(source_id="source", version_id="version", is_demo=is_demo)
    )
    inspector = Mock(side_effect=AssertionError("File inspection must not run"))
    monkeypatch.setattr(source_registration, "inspect_local_original", inspector)
    with pytest.raises(RecordConflict, match="cannot be registered"):
        await source_registration.register_original_file(
            repository,
            context=WorkspaceContext(workspace_id="development"),
            source_id="source",
            version_id="version",
            root=tmp_path,
            path=tmp_path / "arbitrary.pdf",
        )
    inspector.assert_not_called()
    repository.register_local_original.assert_not_called()


def test_cli_failure_does_not_expose_file_or_exception_details(monkeypatch: pytest.MonkeyPatch) -> None:
    """Operator diagnostics stay safe even when filesystem errors contain private paths."""

    async def fail(**_arguments: object) -> None:
        raise OSError("secret-path-and-connection-details")

    monkeypatch.setattr(source_registration, "_register", fail)
    monkeypatch.setattr(
        sys, "argv", ["source-register", "--source-id", "source", "--version-id", "version", "--file", "secret.pdf"]
    )
    with pytest.raises(SystemExit, match="Original registration failed") as failure:
        source_registration.main()
    assert "secret" not in str(failure.value)
