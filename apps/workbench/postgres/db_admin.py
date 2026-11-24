"""Explicit administrator entrypoint; credentials never appear in CLI output."""

import argparse
import json
import os
from dataclasses import asdict

from apps.workbench.postgres.db_migrations import MigrationError, bootstrap_role, downgrade, migrate, migration_status


def main() -> None:
    """Run reviewed database operations using the separate administrator DSN."""
    parser = argparse.ArgumentParser(description="Workbench development database administration")
    parser.add_argument("command", choices=("migrate", "status", "bootstrap-db", "downgrade"))
    parser.add_argument("--confirm-disposable", action="store_true")
    arguments = parser.parse_args()
    dsn = os.environ.get("WORKBENCH_DB_ADMIN_DSN", "")
    if not dsn:
        raise SystemExit("WORKBENCH_DB_ADMIN_DSN is required.")
    try:
        if arguments.command == "bootstrap-db":
            bootstrap_role(dsn, password=os.environ.get("WORKBENCH_DB_APP_PASSWORD", ""))
            print(json.dumps({"status": "application_role_provisioned"}))
            return
        if arguments.command == "migrate":
            status = migrate(dsn)
        elif arguments.command == "downgrade":
            status = downgrade(dsn, confirm_disposable=arguments.confirm_disposable)
        else:
            status = migration_status(dsn)
        print(json.dumps(asdict(status)))
    except MigrationError as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
