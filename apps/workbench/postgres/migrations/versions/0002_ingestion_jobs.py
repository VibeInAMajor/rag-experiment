"""Durable scoped ingestion reservations and confirmed state transitions."""

from pathlib import Path

from alembic import op
from sqlalchemy import text

from apps.workbench.postgres.db_migrations import MIGRATION_TOOL_VERSION, migration_checksum

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None
_DIRECTORY = Path(__file__).resolve().parents[1]


def upgrade() -> None:
    """Add jobs without modifying historical source, version or chunk rows."""
    connection = op.get_bind()
    connection.exec_driver_sql((_DIRECTORY / "0002_ingestion_jobs.up.sql").read_text(encoding="utf-8"))
    connection.execute(
        text(
            "INSERT INTO workbench.schema_migrations(revision,checksum,tool_version) VALUES(:revision,:checksum,:tool)"
        ),
        {"revision": revision, "checksum": migration_checksum(revision=revision), "tool": MIGRATION_TOOL_VERSION},
    )


def downgrade() -> None:
    """Remove jobs only through the migration manager's explicit disposable guard."""
    op.get_bind().exec_driver_sql((_DIRECTORY / "0002_ingestion_jobs.down.sql").read_text(encoding="utf-8"))
