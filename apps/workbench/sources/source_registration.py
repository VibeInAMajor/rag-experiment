"""Trusted local CLI for binding existing real versions to their original files."""

import argparse
import asyncio
import sys
from pathlib import Path

from pydantic import TypeAdapter

from apps.workbench.configuration.config import ApiSettings
from apps.workbench.contracts.schemas import Identifier
from apps.workbench.persistence.models import (
    PersistencePort,
    RecordConflict,
    WorkspaceContext,
    resolve_development_workspace,
)
from apps.workbench.postgres.postgres import PostgresPersistence
from apps.workbench.sources.local_sources import inspect_local_original


async def register_original_file(
    repository: PersistencePort, *, context: WorkspaceContext, source_id: str, version_id: str, root: Path, path: Path
) -> None:
    """
    Bind an existing authorized non-demo active version to inspected file bytes.

    :param repository: Existing scoped registry; this function creates no sources or versions.
    :param context: Server-resolved workspace scope.
    :param source_id: Existing source identity.
    :param version_id: Active source version to associate with the original file.
    :param root: Trusted configured local root.
    :param path: Operator-supplied local file beneath the trusted root.
    :raises RecordConflict: If the version is missing, synthetic, inactive or already bound differently.
    """
    source_id = TypeAdapter(Identifier).validate_python(source_id)
    version_id = TypeAdapter(Identifier).validate_python(version_id)
    record = await repository.get_local_original(context, source_id=source_id, version_id=version_id)
    if record is None or record.is_demo:
        raise RecordConflict("The original cannot be registered for this source version.")
    registration = await asyncio.to_thread(inspect_local_original, root=root, path=path)
    await repository.register_local_original(
        context,
        source_id=source_id,
        version_id=version_id,
        relative_path=registration.relative_path,
        sha256=registration.sha256,
    )


async def _register(*, workspace_id: str, source_id: str, version_id: str, file: Path) -> None:
    settings = ApiSettings.from_env()
    if settings.database_dsn is None or settings.local_source_root is None:
        raise ValueError("The database and local source root must be explicitly configured.")
    context = resolve_development_workspace(workspace_id)
    repository = PostgresPersistence(
        settings.database_dsn.get_secret_value(), snapshot_mode=settings.corpus_snapshot_mode
    )
    try:
        await repository.start()
        await register_original_file(
            repository,
            context=context,
            source_id=source_id,
            version_id=version_id,
            root=Path(settings.local_source_root),
            path=file,
        )
    finally:
        await repository.close()


def main() -> None:
    """Register an original explicitly, with sanitized failures and no HTTP registration."""
    parser = argparse.ArgumentParser(description="Register an original for an existing real active source version.")
    parser.add_argument("--workspace-id", default="development")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--version-id", required=True)
    parser.add_argument("--file", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None) as runner:
            runner.run(
                _register(
                    workspace_id=arguments.workspace_id,
                    source_id=arguments.source_id,
                    version_id=arguments.version_id,
                    file=arguments.file,
                )
            )
    except Exception:
        raise SystemExit(
            "Original registration failed. Check configuration, source/version, file and existing registration."
        ) from None
    print("Original registration complete.")


if __name__ == "__main__":
    main()
