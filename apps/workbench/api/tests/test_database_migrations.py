"""Real PostgreSQL migrations run only against fixture-owned disposable databases."""

import psycopg
import pytest

from apps.workbench.api.db_migrations import HEAD_REVISION, MigrationError, downgrade, migrate, migration_status
from apps.workbench.api.tests.conftest import DisposableDatabase

pytestmark = pytest.mark.integration


def test_fresh_repeat_and_reversible_migrations(disposable_database: DisposableDatabase) -> None:
    """Fresh schema, no-op repeat and guarded rollback share the same reviewed revision."""
    database = disposable_database
    initial = migration_status(database.admin_dsn)
    assert not initial.compatible
    first = migrate(database.admin_dsn)
    assert first.compatible
    assert first.revision == HEAD_REVISION
    assert first.extension_version
    assert migrate(database.admin_dsn) == first
    with pytest.raises(MigrationError):
        downgrade(database.admin_dsn)
    removed = downgrade(database.admin_dsn, confirm_disposable=True)
    assert not removed.compatible
    assert migrate(database.admin_dsn).compatible


def test_wrong_schema_head_is_not_compatible(disposable_database: DisposableDatabase) -> None:
    """A future revision cannot be mistaken for a ready current schema."""
    database = disposable_database
    migrate(database.admin_dsn)
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute("UPDATE workbench.alembic_version SET version_num = 'future_revision'")
    assert not migration_status(database.admin_dsn).compatible
    with pytest.raises(MigrationError):
        migrate(database.admin_dsn)


def test_extension_removal_invalidates_schema_readiness(disposable_database: DisposableDatabase) -> None:
    """A migration number alone does not prove that pgvector is installed."""
    database = disposable_database
    migrate(database.admin_dsn)
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute("DROP EXTENSION vector CASCADE")
    assert not migration_status(database.admin_dsn).compatible


def test_checksum_tampering_invalidates_schema_readiness(disposable_database: DisposableDatabase) -> None:
    """The independently recorded migration checksum participates in compatibility."""
    database = disposable_database
    migrate(database.admin_dsn)
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute("UPDATE workbench.schema_migrations SET checksum = %s", ("0" * 64,))
    assert not migration_status(database.admin_dsn).compatible


def test_disabled_rls_invalidates_schema_readiness(disposable_database: DisposableDatabase) -> None:
    """A matching revision does not certify tables whose isolation policy was disabled."""
    database = disposable_database
    migrate(database.admin_dsn)
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute("ALTER TABLE workbench.chunks DISABLE ROW LEVEL SECURITY")
    assert not migration_status(database.admin_dsn).compatible


def test_application_role_is_restricted_and_cannot_migrate(disposable_database: DisposableDatabase) -> None:
    """Application sessions have data privileges without schema administration."""
    database = disposable_database
    migrate(database.admin_dsn)
    with psycopg.connect(database.app_dsn) as connection:
        attributes = connection.execute(
            "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
        assert attributes == (False, False, False, False)
    with psycopg.connect(database.app_dsn) as connection, pytest.raises(psycopg.errors.InsufficientPrivilege):
        connection.execute("CREATE TABLE workbench.must_not_exist (id integer)")
    with psycopg.connect(database.app_dsn) as connection, pytest.raises(psycopg.errors.InsufficientPrivilege):
        connection.execute(
            "INSERT INTO workbench.embedding_profiles (profile_id, dimensions, purpose) VALUES ('bad', 3, 'synthetic')"
        )
