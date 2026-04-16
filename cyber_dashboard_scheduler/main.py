"""Minimal entrypoint for the scheduler application."""

from __future__ import annotations

import logging


LOGGER = logging.getLogger(__name__)


def main() -> None:
    """Start the scheduler bootstrap."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    LOGGER.info("cyber-dashboard-scheduler bootstrap ready")


if __name__ == "__main__":
    main()
