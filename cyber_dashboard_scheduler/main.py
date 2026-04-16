"""Point d'entrée exécutable pour l'application scheduler."""

from __future__ import annotations

import logging

from cyber_dashboard_scheduler.config import ConfigurationError, Settings
from cyber_dashboard_scheduler.utils.logging import configure_logging


LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Charge la configuration et démarre le bootstrap du scheduler."""
    try:
        settings = Settings.from_env()
    except ConfigurationError as exc:
        configure_logging("ERROR")
        LOGGER.error("Échec du démarrage du scheduler : %s", exc)
        return 1

    configure_logging(settings.log_level)
    LOGGER.info(
        "Configuration du scheduler chargée pour la base %s:%s/%s",
        settings.database.host,
        settings.database.port,
        settings.database.name,
    )
    LOGGER.info(
        "Scheduler démarré avec succès avec une limite de %s requêtes/jour",
        settings.limit_request_per_day,
    )
    LOGGER.info("L'inventaire et la collecte d'attaques sont désactivés à cette étape")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
