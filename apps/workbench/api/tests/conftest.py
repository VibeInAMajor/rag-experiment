"""Disposable PostgreSQL databases; never reset the configured application database."""

import asyncio
import os
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo


def pytest_asyncio_loop_factories() -> dict[str, Callable[[], asyncio.AbstractEventLoop]]:
    """Use psycopg's required selector loop on Windows without global policy mutation."""
    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else asyncio.new_event_loop
    return {"database-compatible": factory}


@dataclass(frozen=True)
class DisposableDatabase:
    name: str
    admin_dsn: str = field(repr=False)
    app_dsn: str = field(repr=False)


@pytest.fixture
def disposable_database() -> Iterator[DisposableDatabase]:
    """Create and destroy only a new UUID-named database owned by this fixture."""
    admin_dsn = os.environ.get("WORKBENCH_TEST_ADMIN_DSN")
    app_dsn = os.environ.get("WORKBENCH_TEST_APP_DSN")
    if not admin_dsn or not app_dsn:
        pytest.skip("Explicit WORKBENCH_TEST_ADMIN_DSN and WORKBENCH_TEST_APP_DSN are required")
    name = f"rag_test_{uuid4().hex}"
    database = DisposableDatabase(
        name=name, admin_dsn=make_conninfo(admin_dsn, dbname=name), app_dsn=make_conninfo(app_dsn, dbname=name)
    )
    control_dsn = make_conninfo(admin_dsn, dbname="postgres")
    with psycopg.connect(control_dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield database
    finally:
        if not name.startswith("rag_test_") or conninfo_to_dict(database.admin_dsn)["dbname"] != name:
            raise RuntimeError("Refusing to remove a database not owned by the disposable fixture")
        with psycopg.connect(control_dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
