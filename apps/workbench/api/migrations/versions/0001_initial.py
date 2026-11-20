"""Initial scoped registry and nullable vector storage."""

from pathlib import Path

from alembic import op
from sqlalchemy import text

from apps.workbench.api.db_migrations import MIGRATION_TOOL_VERSION, migration_checksum

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None
_DIRECTORY = Path(__file__).resolve().parents[1]


def upgrade() -> None:
    """Create the reviewed initial schema and audit its exact SQL."""
    connection = op.get_bind()
    connection.exec_driver_sql((_DIRECTORY / "0001_initial.up.sql").read_text(encoding="utf-8"))
    connection.execute(
        text(
            "INSERT INTO workbench.schema_migrations (revision, checksum, tool_version) "
            "VALUES (:revision, :checksum, :tool)"
        ),
        {"revision": revision, "checksum": migration_checksum(), "tool": MIGRATION_TOOL_VERSION},
    )


def downgrade() -> None:
    """Drop only the reviewed schema objects in a guarded disposable database."""
    op.get_bind().exec_driver_sql((_DIRECTORY / "0001_initial.down.sql").read_text(encoding="utf-8"))
