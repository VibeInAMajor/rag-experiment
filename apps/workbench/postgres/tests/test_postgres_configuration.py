"""Infrastructure admission bounds are checked before any connection is attempted."""

from typing import Any

import pytest

from apps.workbench.postgres.postgres import PostgresPersistence


@pytest.mark.parametrize(
    "bounds",
    [
        {"min_size": 0},
        {"min_size": 4, "max_size": 2},
        {"max_size": 17},
        {"timeout": 0.0},
        {"timeout": 31.0},
        {"statement_timeout_ms": 0},
        {"statement_timeout_ms": 30001},
    ],
)
def test_pool_and_query_timeouts_reject_unbounded_configuration(bounds: dict[str, Any]) -> None:
    """Invalid bounds fail independently of database availability or credentials."""
    with pytest.raises(ValueError, match="Invalid database pool bounds"):
        PostgresPersistence("not-a-connection-string", **bounds)
