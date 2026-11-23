"""Add durable tenant-scoped semantic jobs and immutable vector cache namespaces."""

from pathlib import Path

from alembic import op
from sqlalchemy import text

from apps.workbench.api.db_migrations import MIGRATION_TOOL_VERSION, migration_checksum

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None
_DIRECTORY = Path(__file__).resolve().parents[1]


def upgrade() -> None:
    """Keep lexical publication separate while adding resumable semantic checkpoints."""
    connection = op.get_bind()
    connection.exec_driver_sql(
        (_DIRECTORY / "0005_embedding_jobs.up.sql").read_text(encoding="utf-8"),
        execution_options={"no_parameters": True},
    )
    connection.execute(
        text(
            "INSERT INTO workbench.schema_migrations(revision,checksum,tool_version) VALUES(:revision,:checksum,:tool)"
        ),
        {"revision": revision, "checksum": migration_checksum(revision=revision), "tool": MIGRATION_TOOL_VERSION},
    )


def downgrade() -> None:
    """Drop only the additive semantic layer under the existing disposable database guard."""
    op.get_bind().exec_driver_sql((_DIRECTORY / "0005_embedding_jobs.down.sql").read_text(encoding="utf-8"))
