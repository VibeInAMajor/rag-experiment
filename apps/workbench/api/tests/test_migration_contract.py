"""Migration identity must survive the supported Windows and Linux checkouts."""

from pathlib import Path

import pytest

from apps.workbench.api import db_migrations


def test_migration_checksum_is_independent_of_checkout_line_endings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CRLF preserves the applied revision while actual SQL changes remain detectable."""
    originals = {
        filename: (db_migrations._DIRECTORY / filename).read_text(encoding="utf-8")
        for filename in ("0001_initial.up.sql", "0001_initial.down.sql")
    }
    for filename, content in originals.items():
        (tmp_path / filename).write_bytes(content.encode("utf-8"))
    monkeypatch.setattr(db_migrations, "_DIRECTORY", tmp_path)
    unix_checksum = db_migrations.migration_checksum()
    for filename, content in originals.items():
        (tmp_path / filename).write_bytes(content.replace("\n", "\r\n").encode("utf-8"))
    assert db_migrations.migration_checksum() == unix_checksum
    with (tmp_path / "0001_initial.up.sql").open("ab") as altered:
        altered.write(b"-- changed reviewed SQL\r\n")
    assert db_migrations.migration_checksum() != unix_checksum
