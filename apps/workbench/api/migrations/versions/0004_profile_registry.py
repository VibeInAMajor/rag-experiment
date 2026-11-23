"""Persist immutable retrieval policies and audited workspace lifecycle selections."""

from pathlib import Path

from alembic import op
from sqlalchemy import text

from apps.workbench.api.db_migrations import MIGRATION_TOOL_VERSION, migration_checksum

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None
_DIRECTORY = Path(__file__).resolve().parents[1]


def upgrade() -> None:
    """Add profile governance without rewriting corpus or historical migration rows."""
    connection = op.get_bind()
    connection.exec_driver_sql((_DIRECTORY / "0004_profile_registry.up.sql").read_text(encoding="utf-8"))
    connection.execute(
        text(
            "INSERT INTO workbench.schema_migrations(revision,checksum,tool_version) VALUES(:revision,:checksum,:tool)"
        ),
        {"revision": revision, "checksum": migration_checksum(revision=revision), "tool": MIGRATION_TOOL_VERSION},
    )


def downgrade() -> None:
    """Remove governance only under the migration manager's explicit disposable guard."""
    op.get_bind().exec_driver_sql((_DIRECTORY / "0004_profile_registry.down.sql").read_text(encoding="utf-8"))
