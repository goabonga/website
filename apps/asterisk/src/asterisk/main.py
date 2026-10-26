# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Entry point of the asterisk voice bot daemon."""

import asyncio
import logging
import sys

from asterisk import __version__
from asterisk.config import config


def setup_logging():
    """Configure logging with stdout for INFO and stderr for ERROR."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.LOG_LEVEL))

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Handler for INFO and below -> stdout
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.addFilter(lambda record: record.levelno < logging.ERROR)
    stdout_handler.setFormatter(formatter)

    # Handler for ERROR and above -> stderr
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(formatter)

    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)


logger = logging.getLogger(__name__)


def log_configuration():
    """Log the effective configuration."""
    logger.info(
        f"asterisk {__version__}: AudioSocket address "
        f"{config.AUDIOSOCKET_HOST}:{config.AUDIOSOCKET_PORT}"
    )


async def main():
    """Run the daemon."""
    log_configuration()


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
