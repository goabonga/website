# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Entry point of the asterisk voice bot daemon."""

import asyncio
import functools
import logging
import signal
import sys

from asterisk import __version__
from asterisk.audiosocket import AudioSocketServer
from asterisk.call_handler import handle_call
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


async def shutdown(server: AudioSocketServer, sig: signal.Signals):
    """Graceful shutdown handler."""
    logger.info(f"Received signal {sig.name}, shutting down...")

    await server.stop()

    logger.info("Shutdown complete")


async def main():
    """Start the AudioSocket server."""
    log_configuration()

    server = AudioSocketServer(config.AUDIOSOCKET_HOST, config.AUDIOSOCKET_PORT)
    server.set_handler(handle_call)

    # Set up signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()

    def schedule_shutdown(sig: signal.Signals) -> None:
        asyncio.create_task(shutdown(server, sig))

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, functools.partial(schedule_shutdown, sig))

    logger.info(
        f"Starting AudioSocket server on {config.AUDIOSOCKET_HOST}:{config.AUDIOSOCKET_PORT}"
    )

    try:
        await server.start()
    except asyncio.CancelledError:
        logger.info("Server task cancelled")


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
