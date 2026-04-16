"""Point d'entrée exécutable pour l'application scheduler."""

from __future__ import annotations

import logging

from cyber_dashboard_scheduler.clients import SerenicityApiClient
from cyber_dashboard_scheduler.config import ConfigurationError, Settings
from cyber_dashboard_scheduler.db import PostgresDatabase
from cyber_dashboard_scheduler.services import SourceInventoryService
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
    LOGGER.info(
        "Timeout HTTP configuré à %.1f secondes",
        settings.http_timeout_seconds,
    )

    database = PostgresDatabase(settings.database)
    try:
        database.check_connection()
    except RuntimeError as exc:
        LOGGER.error("Connexion PostgreSQL impossible avant inventaire : %s", exc)
        return 1

    serenicity_client = SerenicityApiClient(
        base_url=settings.serenicity.base_url,
        api_key=settings.serenicity.api_key,
        timeout_seconds=settings.http_timeout_seconds,
    )
    inventory_service = SourceInventoryService(
        settings=settings,
        database=database,
        serenicity_client=serenicity_client,
    )

    try:
        result = inventory_service.run_once()
    except Exception as exc:
        LOGGER.error("Échec inattendu pendant l'inventaire des sources : %s", exc)
        return 1

    LOGGER.info(
        "Inventaire exécuté. endpoints=%s persistes=%s desactivees=%s ignorees=%s erreurs=%s",
        ", ".join(result.endpoints_called) or "aucun",
        result.sources_persisted,
        result.sources_deactivated,
        result.sources_skipped,
        result.source_errors,
    )
    LOGGER.info("Fin du scheduler après un inventaire unique")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
