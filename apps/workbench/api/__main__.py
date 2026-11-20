"""Start the loopback development listener with access-payload logging disabled."""

import logging
import sys

import uvicorn
from pydantic import ValidationError

from apps.workbench.api.config import ApiSettings


def main() -> None:
    """Validate settings and start the isolated loopback listener."""
    try:
        settings = ApiSettings.from_env()
    except (ValueError, ValidationError):
        raise SystemExit("Invalid Workbench API configuration.") from None
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    uvicorn.run(
        "apps.workbench.api.application:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        access_log=False,
    )


if __name__ == "__main__":
    main()
