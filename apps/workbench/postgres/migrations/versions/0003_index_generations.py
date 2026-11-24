"""Persist committed corpus snapshots without changing existing corpus records."""

from pathlib import Path

from alembic import op
from sqlalchemy import text

from apps.workbench.postgres.db_migrations import MIGRATION_TOOL_VERSION, migration_checksum

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None
_DIRECTORY = Path(__file__).resolve().parents[1]


def upgrade() -> None:
    """Backfill the immutable ledger and current manifest once."""
    connection = op.get_bind()
    connection.exec_driver_sql(
        (_DIRECTORY / "0003_index_generations.up.sql").read_text(encoding="utf-8"),
        execution_options={"no_parameters": True},
    )
    connection.execute(
        text(
            "INSERT INTO workbench.schema_migrations(revision,checksum,tool_version) VALUES(:revision,:checksum,:tool)"
        ),
        {"revision": revision, "checksum": migration_checksum(revision=revision), "tool": MIGRATION_TOOL_VERSION},
    )


def downgrade() -> None:
    """Remove derived snapshots only via the disposable rollback guard."""
    op.get_bind().exec_driver_sql((_DIRECTORY / "0003_index_generations.down.sql").read_text(encoding="utf-8"))
