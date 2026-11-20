"""Run with hatch -e test run python -m apps.workbench.validator."""

import contextlib
import logging

from apps.workbench.validator.server import create_server


def main() -> None:
    """Start the isolated constructor-only service on its fixed loopback port."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with create_server() as server:
        logging.info("Haystack validation: http://127.0.0.1:8010")
        with contextlib.suppress(KeyboardInterrupt):
            server.serve_forever()


if __name__ == "__main__":
    main()
