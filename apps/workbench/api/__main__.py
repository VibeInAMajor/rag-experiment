"""Start the loopback development listener with access-payload logging disabled."""

import asyncio
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
    server = uvicorn.Server(
        uvicorn.Config(
            "apps.workbench.api.application:create_app",
            factory=True,
            host=settings.host,
            port=settings.port,
            access_log=False,
            loop="asyncio",
        )
    )
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    try:
        with asyncio.Runner(loop_factory=loop_factory) as runner:
            runner.run(server.serve())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
