"""
Logger Configuration Utility
Provides a centralized, formatted, and colorized logging system for the application.
"""

import logging
import sys


def setup_logger(name: str = "MovieBot") -> logging.Logger:
    """Creates and returns a structured logger with stdout handler."""
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(logging.INFO)

        # Formatter including timestamp, log level, module name, and message
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Standard Output Handler (Render logs reader compatible)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logger
