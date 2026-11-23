"""Explicit Alembic migrations with audited SQL and disposable-only rollback."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Connection
from sqlalchemy.pool import NullPool

HEAD_REVISION = "0003"
EXPECTED_REVISION = HEAD_REVISION
MIGRATION_TOOL_VERSION = "alembic-1.20.1"
_EXTENSION_VERSION = "0.8.2"
_DIRECTORY = Path(__file__).resolve().parent / "migrations"
_LOCK_KEY = 719342176213
_TABLES = ("workspaces", "sources", "source_versions", "chunks", "embedding_profiles")
_SCOPED_TABLES = ("workspaces", "sources", "source_versions", "chunks")
_REVISIONS = (("0001", "0001_initial"), ("0002", "0002_ingestion_jobs"), ("0003", "0003_index_generations"))


class MigrationError(ValueError):
    """The database cannot safely accept this migration operation."""


@dataclass(frozen=True)
class MigrationStatus:
    revision: str | None
    expected_revision: str = HEAD_REVISION
    compatible: bool = False
    extension_version: str | None = None
    reason: str = "NOT_MIGRATED"


def migration_checksum(*, revision: str = "0001") -> str:
    """Fingerprint one reviewed migration; the default preserves historical 0001 callers."""
    stem = dict(_REVISIONS).get(revision)
    if stem is None:
        raise MigrationError("Unknown migration revision.")
    digest = sha256()
    for filename in (f"{stem}.up.sql", f"{stem}.down.sql"):
        digest.update(filename.encode("ascii"))
        digest.update(b"\0")
        # Git checkouts may use CRLF on Windows; line endings do not change SQL.
        digest.update((_DIRECTORY / filename).read_text(encoding="utf-8").encode("utf-8"))
    return digest.hexdigest()


def migration_ledger(revision: str) -> list[tuple[str, str, str]]:
    """Return the exact checksum ledger required by an applied supported revision."""
    revisions = [item[0] for item in _REVISIONS]
    if revision not in revisions:
        raise MigrationError("Unknown migration revision.")
    return [
        (applied, migration_checksum(revision=applied), MIGRATION_TOOL_VERSION)
        for applied in revisions[: revisions.index(revision) + 1]
    ]


@contextmanager
def _connection(dsn: str, *, transaction: bool = False) -> Iterator[Connection]:
    engine = create_engine(
        URL.create(drivername="postgresql+psycopg"),
        creator=lambda: psycopg.connect(dsn, connect_timeout=5),
        poolclass=NullPool,
        hide_parameters=True,
    )
    try:
        with engine.connect() as connection, connection.begin():
            connection.execute(text("SELECT set_config('statement_timeout', '10000', true)"))
            connection.execute(text("SELECT set_config('lock_timeout', '5000', true)"))
            if transaction:
                connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _LOCK_KEY})
            yield connection
    finally:
        engine.dispose()


def _status(connection: Connection) -> MigrationStatus:
    extension = connection.execute(
        text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    ).scalar_one_or_none()
    version_table = connection.execute(text("SELECT to_regclass('workbench.alembic_version')")).scalar_one_or_none()
    if version_table is None:
        return MigrationStatus(revision=None, extension_version=extension)
    revisions = list(connection.execute(text("SELECT version_num FROM workbench.alembic_version")).scalars())
    if not revisions:
        return MigrationStatus(revision=None, extension_version=extension)
    revision = revisions[0]
    if len(revisions) != 1 or revision not in dict(_REVISIONS):
        return MigrationStatus(revision=revision, extension_version=extension, reason="SCHEMA_INCOMPATIBLE")
    ledger_table = connection.execute(text("SELECT to_regclass('workbench.schema_migrations')")).scalar_one_or_none()
    if ledger_table is None:
        return MigrationStatus(revision=revision, extension_version=extension, reason="CHECKSUM_MISMATCH")
    ledger = connection.execute(
        text("SELECT revision, checksum, tool_version FROM workbench.schema_migrations ORDER BY revision")
    ).all()
    if [tuple(row) for row in ledger] != migration_ledger(revision):
        return MigrationStatus(revision=revision, extension_version=extension, reason="CHECKSUM_MISMATCH")
    if extension != _EXTENSION_VERSION:
        return MigrationStatus(revision=revision, extension_version=extension, reason="EXTENSION_INCOMPATIBLE")
    required_tables = _TABLES + (("ingestion_jobs",) if revision >= "0002" else ())
    if revision >= "0003":
        required_tables += ("corpus_index_state", "index_generations", "corpus_source_state")
    tables_exist = all(
        connection.execute(text("SELECT to_regclass(:table)"), {"table": f"workbench.{table}"}).scalar_one_or_none()
        is not None
        for table in required_tables
    ) and _scoping_enabled(connection, ingestion=revision >= "0002", indexes=revision >= "0003")
    return MigrationStatus(
        revision=revision,
        extension_version=extension,
        compatible=tables_exist,
        reason=("COMPATIBLE" if revision == HEAD_REVISION else "UPGRADE_AVAILABLE")
        if tables_exist
        else "SCHEMA_INCOMPATIBLE",
    )


def _scoping_enabled(connection: Connection, *, ingestion: bool = False, indexes: bool = False) -> bool:
    tables = _SCOPED_TABLES + (("ingestion_jobs",) if ingestion else ())
    if indexes:
        tables += ("corpus_index_state", "index_generations", "corpus_source_state")
    rows = connection.execute(
        text(
            "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, pg_get_userbyid(c.relowner) "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='workbench' AND c.relname = ANY(:tables)"
        ),
        {"tables": list(tables)},
    ).all()
    protected = len(rows) == len(tables) and all(row[1] and row[2] and row[3] != "workbench_app" for row in rows)
    if not indexes or not protected:
        return protected
    enabled_triggers: int = connection.execute(
        text(
            "SELECT count(*) FROM pg_trigger WHERE tgenabled IN ('O','A') AND "
            "(tgrelid,tgname) IN (('workbench.workspaces'::regclass,'initialize_corpus_index'),"
            "('workbench.sources'::regclass,'dirty_source_index'),"
            "('workbench.source_versions'::regclass,'dirty_version_index'),"
            "('workbench.chunks'::regclass,'dirty_chunk_index'),"
            "('workbench.index_generations'::regclass,'immutable_index_generation'),"
            "('workbench.corpus_index_state'::regclass,'corpus_generation_transition'))"
        )
    ).scalar_one()
    return enabled_triggers == 6


def migration_status(dsn: str) -> MigrationStatus:
    """Inspect migration, audited SQL and extension compatibility without DDL."""
    try:
        with _connection(dsn) as connection:
            return _status(connection)
    except Exception:
        raise MigrationError("Migration status is unavailable.") from None


def _configuration(connection: Connection) -> Config:
    configuration = Config()
    configuration.set_main_option("script_location", str(_DIRECTORY))
    configuration.attributes["connection"] = connection
    return configuration


def _ensure_role(connection: Connection) -> None:
    current: str = connection.execute(text("SELECT current_user")).scalar_one()
    if current == "workbench_app":
        raise MigrationError("Use the separate migration administrator.")
    connection.exec_driver_sql(
        """DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'workbench_app') THEN
            CREATE ROLE workbench_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
        END IF;
        END $$"""
    )
    unsafe: bool = connection.execute(
        text(
            "SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls "
            "FROM pg_roles WHERE rolname = 'workbench_app'"
        )
    ).scalar_one()
    if unsafe:
        raise MigrationError("The application role has unsafe privileges.")


def _grant_application(connection: Connection) -> None:
    connection.exec_driver_sql("GRANT USAGE ON SCHEMA workbench TO workbench_app")
    connection.exec_driver_sql(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON workbench.workspaces, workbench.sources, "
        "workbench.source_versions, workbench.chunks TO workbench_app"
    )
    connection.exec_driver_sql(
        "GRANT SELECT ON workbench.embedding_profiles, workbench.schema_migrations, "
        "workbench.alembic_version TO workbench_app"
    )
    connection.exec_driver_sql("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    if connection.execute(text("SELECT to_regclass('workbench.ingestion_jobs')")).scalar_one_or_none() is not None:
        connection.exec_driver_sql("GRANT SELECT,INSERT,UPDATE ON workbench.ingestion_jobs TO workbench_app")
    if connection.execute(text("SELECT to_regclass('workbench.corpus_index_state')")).scalar_one_or_none() is not None:
        connection.exec_driver_sql(
            "GRANT SELECT ON workbench.corpus_index_state,workbench.index_generations,"
            "workbench.corpus_source_state TO workbench_app"
        )


def _migrate(connection: Connection) -> MigrationStatus:
    before = _status(connection)
    if before.revision is not None and not before.compatible:
        raise MigrationError("The existing migration state is incompatible.")
    _ensure_role(connection)
    if before.revision is None:
        existing: int = connection.execute(
            text("SELECT count(*) FROM pg_tables WHERE schemaname = 'workbench' AND tablename != 'alembic_version'")
        ).scalar_one()
        if existing:
            raise MigrationError("An unversioned application schema already exists.")
        connection.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS workbench")
    command.upgrade(_configuration(connection), "head")
    _grant_application(connection)
    after = _status(connection)
    if not after.compatible:
        raise MigrationError("The resulting migration state is incompatible.")
    return after


def migrate(dsn: str) -> MigrationStatus:
    """Apply known revisions atomically under an advisory lock; reject drift."""
    try:
        with _connection(dsn, transaction=True) as connection:
            return _migrate(connection)
    except MigrationError:
        raise
    except Exception:
        raise MigrationError("The database migration failed.") from None


def _downgrade(connection: Connection) -> MigrationStatus:
    database: str = connection.execute(text("SELECT current_database()")).scalar_one()
    if re.fullmatch(r"(?:rag_test|workbench_test|workbench_disposable)_[a-zA-Z0-9_]+", database) is None:
        raise MigrationError("Rollback is restricted to named disposable databases.")
    _ensure_role(connection)
    if not _status(connection).compatible:
        raise MigrationError("The migration state is incompatible.")
    command.downgrade(_configuration(connection), "base")
    return _status(connection)


def downgrade(dsn: str, *, confirm_disposable: bool = False) -> MigrationStatus:
    """Roll back only explicitly confirmed disposable test databases."""
    if not confirm_disposable:
        raise MigrationError("Disposable database confirmation is required.")
    try:
        with _connection(dsn, transaction=True) as connection:
            return _downgrade(connection)
    except MigrationError:
        raise
    except Exception:
        raise MigrationError("The database rollback failed.") from None


def bootstrap_role(dsn: str, *, password: str) -> None:
    """Provision the restricted login using a runtime-only password parameter."""
    if not password or "\0" in password:
        raise MigrationError("A valid application password is required.")
    try:
        with _connection(dsn, transaction=True) as connection:
            _ensure_role(connection)
            connection.execute(
                text("SELECT set_config('workbench.bootstrap_password', :password, true)"), {"password": password}
            )
            connection.exec_driver_sql(
                """DO $$ BEGIN
                EXECUTE 'ALTER ROLE workbench_app LOGIN PASSWORD ' ||
                    quote_literal(current_setting('workbench.bootstrap_password'));
                END $$"""
            )
            if _status(connection).compatible:
                _grant_application(connection)
    except MigrationError:
        raise
    except Exception:
        raise MigrationError("Application role provisioning failed.") from None
