"""Supervised browser fixture: real isolated PostgreSQL and actual Windows Explorer dispatch."""

import asyncio
import json
import os
import re
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import uvicorn
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from pydantic import SecretStr

from apps.workbench.api.application import create_app
from apps.workbench.configuration.config import ApiSettings
from apps.workbench.persistence.models import Chunk, Source, SourceVersion, Workspace, resolve_development_workspace
from apps.workbench.postgres.db_migrations import migrate
from apps.workbench.postgres.postgres import PostgresPersistence
from apps.workbench.sources.source_registration import register_original_file

_PORT = 8014
_SOURCE_ID = "browser-original"
_VERSION_ID = "browser-original-v1"
_CHUNK_ID = "browser-original-chunk-1"
_FILENAME = "Retention original, проверка.txt"
_CONTENT = "Retention policy for the original browser fixture. GIN lexical retrieval preserves source provenance.\n"


@contextmanager
def _owned_database() -> Iterator[tuple[str, str]]:
    admin_base = os.environ.get("WORKBENCH_DB_ADMIN_DSN")
    app_base = os.environ.get("WORKBENCH_DB_DSN")
    if not admin_base or not app_base:
        raise ValueError("Explicit local administrator and application connections are required.")
    name = f"rag_test_{uuid4().hex}"
    control = make_conninfo(admin_base, dbname="postgres")
    admin = make_conninfo(admin_base, dbname=name)
    application = urlunsplit(urlsplit(app_base)._replace(path=f"/{name}"))
    with psycopg.connect(control, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    print(json.dumps({"event": "source_fixture_created", "database": name}), flush=True)
    try:
        yield admin, application
    finally:
        if re.fullmatch(r"rag_test_[a-f0-9]{32}", name) is None or any(
            conninfo_to_dict(dsn)["dbname"] != name for dsn in (admin, application)
        ):
            raise RuntimeError("Refusing cleanup outside the owned disposable database.")
        with psycopg.connect(control, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
        print(json.dumps({"event": "source_fixture_cleaned", "database": name}), flush=True)


async def _prepare(*, dsn: str, root: Path, original: Path) -> None:
    repository = PostgresPersistence(dsn)
    context = resolve_development_workspace()
    try:
        await repository.start()
        await repository.create_workspace(context, Workspace(workspace_id=context.workspace_id, name="Development"))
        fingerprint = sha256(_CONTENT.encode("utf-8")).hexdigest()
        source = Source(workspace_id=context.workspace_id, source_id=_SOURCE_ID, title=_FILENAME)
        version = SourceVersion(
            workspace_id=context.workspace_id,
            source_id=_SOURCE_ID,
            version_id=_VERSION_ID,
            content_hash=fingerprint,
            metadata={"test_harness": "supervised-browser-original"},
        )
        chunk = Chunk(
            workspace_id=context.workspace_id,
            source_id=_SOURCE_ID,
            version_id=_VERSION_ID,
            chunk_id=_CHUNK_ID,
            title=source.title,
            content=_CONTENT,
            content_hash=fingerprint,
        )
        await repository.publish_source(context, source=source, version=version, chunks=[chunk])
        await register_original_file(
            repository, context=context, source_id=_SOURCE_ID, version_id=_VERSION_ID, root=root, path=original
        )
    finally:
        await repository.close()


async def _serve(*, dsn: str, root: Path) -> None:
    app = create_app(settings=ApiSettings(port=_PORT, database_dsn=SecretStr(dsn), local_source_root=str(root)))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=_PORT, access_log=False, loop="asyncio"))
    serving = asyncio.create_task(server.serve())
    while not server.started:
        if serving.done():
            await serving
            raise RuntimeError("The browser fixture listener did not start.")
        await asyncio.sleep(0.05)
    print(
        json.dumps(
            {
                "event": "source_fixture_ready",
                "port": _PORT,
                "source_id": _SOURCE_ID,
                "version_id": _VERSION_ID,
                "chunk_id": _CHUNK_ID,
                "name": _FILENAME,
                "launcher": "actual_windows_explorer",
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    await serving


def main() -> None:
    """Serve only a fresh owned test database until the supervising operator stops it."""
    # Keep this owned temporary original after shutdown so Explorer's selected file remains valid.
    root = Path(tempfile.mkdtemp(prefix="rag-source-browser-"))
    original = root / _FILENAME
    content = _CONTENT.encode("utf-8")
    original.write_bytes(content)
    try:
        with _owned_database() as (admin, application):
            migrate(admin)
            with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None) as runner:
                runner.run(_prepare(dsn=application, root=root, original=original))
                runner.run(_serve(dsn=application, root=root))
    except KeyboardInterrupt:
        pass
    except Exception:
        raise SystemExit("Source fixture failed. Check the isolated test configuration.") from None


if __name__ == "__main__":
    main()
