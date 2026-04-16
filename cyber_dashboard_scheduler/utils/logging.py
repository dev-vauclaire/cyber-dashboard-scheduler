"""Utilitaires de journalisation du scheduler."""

from __future__ import annotations

import logging


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s - %(message)s"


def configure_logging(level_name: str) -> None:
    """Initialise la journalisation de l'application avec un format homogène."""
    logging.basicConfig(
        level=getattr(logging, level_name.upper(), logging.INFO),
        format=LOG_FORMAT,
        force=True,
    )
