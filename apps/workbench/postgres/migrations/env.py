"""Run only against the explicit, transaction-owned migration connection."""

from alembic import context

connection = context.config.attributes["connection"]
context.configure(connection=connection, version_table_schema="workbench", transactional_ddl=True)
with context.begin_transaction():
    context.run_migrations()
