"""
Logging configuration for the application.

This module provides a setup function to configure the Loguru logger.
It should be called once at the application's entry point.
"""

import sys

from loguru import logger

from bot.core.config import OUTPUT_DIR
from bot.core.config import settings


log = logger.bind(name=settings.APP_NAME)


def setup_logging():
    """
    Configures the application's logger.

    This function should be called once when the application starts.
    It removes default handlers, creates the log directory, and adds
    configured sinks for file and console logging.
    """
    # 1. Remove the default handler to prevent duplicate logs in the console.
    logger.remove()

    # 2. Ensure the output directory for logs exists.
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.error(f"Failed to create log directory {OUTPUT_DIR}: {e}")
        sys.exit(1)

    # 3. Add a sink for writing logs to a file.
    log.add(
        sink=settings.LOG_FILE,
        level=settings.LOG_LEVEL.upper(),
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} |"
        " {level: <8} | [{extra[name]}] | {name}:{function}:{line} - {message}",
        rotation="500 KB",
        enqueue=True,  # Makes logging non-blocking
        backtrace=True,  # Set to False in production for security
        diagnose=True,  # Set to False in production for security
        catch=True,  # Catches exceptions in other modules
    )

    # 4. Add a sink for colored console output for development.
    log.add(
        sink=sys.stderr,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> |"
        " <level>{level: <8}</level> |"
        " <cyan>{name}</cyan>:<cyan>{function}</cyan>"
        " - <level>{message}</level>",
        colorize=True,
    )

    log.info("Logger has been configured.")
