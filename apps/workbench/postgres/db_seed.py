"""Explicit deterministic development seed; never invoked by API startup."""

import asyncio
import json
import os
import sys
from hashlib import sha256
from pathlib import Path

from pydantic import JsonValue

from apps.workbench.persistence.models import (
    Chunk,
    PersistenceError,
    Source,
    SourceVersion,
    Workspace,
    resolve_development_workspace,
)
from apps.workbench.postgres.postgres import PostgresPersistence

_FIXTURE = Path(__file__).parent / "fixtures" / "development-corpus.json"
_SEED_METADATA: dict[str, JsonValue] = {"development_seed": "development-corpus-v1", "synthetic": True}


def development_documents() -> list[tuple[Source, SourceVersion, list[Chunk]]]:
    """Load the reviewed, non-sensitive passages with deterministic provenance."""
    entries = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    documents = []
    for entry in entries:
        digest = sha256(entry["content"].encode("utf-8")).hexdigest()
        source_id = entry["source_id"]
        version_id = f"{source_id}-v1"
        source = Source(workspace_id="development", source_id=source_id, title=entry["title"], metadata=_SEED_METADATA)
        version = SourceVersion(
            workspace_id="development",
            source_id=source_id,
            version_id=version_id,
            content_hash=digest,
            metadata=_SEED_METADATA,
        )
        chunk = Chunk(
            workspace_id="development",
            source_id=source_id,
            version_id=version_id,
            chunk_id=f"{source_id}-chunk-1",
            title=entry["title"],
            content=entry["content"],
            content_hash=digest,
            metadata=_SEED_METADATA,
        )
        documents.append((source, version, [chunk]))
    return documents


async def seed_development(repository: PostgresPersistence) -> int:
    """Insert all demo records atomically, or confirm their exact existing identity."""
    return await repository.seed_development(
        resolve_development_workspace(),
        workspace=Workspace(workspace_id="development", name="Development", metadata=_SEED_METADATA),
        documents=development_documents(),
    )


async def _seed() -> int:
    dsn = os.environ.get("WORKBENCH_DB_DSN")
    if not dsn:
        raise SystemExit("WORKBENCH_DB_DSN must contain the application connection settings.")
    repository = PostgresPersistence(dsn)
    try:
        await repository.start()
        return await seed_development(repository)
    except PersistenceError:
        raise SystemExit("Development seed failed; check database readiness and seed ownership.") from None
    finally:
        await repository.close()


def main() -> None:
    """Run the explicitly requested seed without revealing connection settings."""
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None) as runner:
        inserted = runner.run(_seed())
    print(f"Development seed complete: {inserted} sources inserted.")


if __name__ == "__main__":
    main()
