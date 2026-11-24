"""Connection identities for isolated Workbench test databases."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DisposableDatabase:
    name: str
    admin_dsn: str = field(repr=False)
    app_dsn: str = field(repr=False)
