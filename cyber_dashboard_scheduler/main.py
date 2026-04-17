"""Point d'entrée exécutable pour l'application scheduler."""

from __future__ import annotations

import logging

from cyber_dashboard_scheduler.clients import (
    OgoApiClient,
    SerenicityLurioClient,
    SerenicitySensorClient,
)
from cyber_dashboard_scheduler.config import ConfigurationError, Settings
from cyber_dashboard_scheduler.db import PostgresDatabase
from cyber_dashboard_scheduler.services import (
    LurioAttackCollectionService,
    OgoAttackCollectionService,
    SerenicitySensorAttackCollectionService,
    SourceInventoryService,
)
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

    lurio_client = SerenicityLurioClient(
        base_url=settings.serenicity.base_url,
        api_key=settings.serenicity.api_key,
        timeout_seconds=settings.http_timeout_seconds,
    )
    sensor_client = SerenicitySensorClient(
        base_url=settings.serenicity.base_url,
        api_key=settings.serenicity.api_key,
        timeout_seconds=settings.http_timeout_seconds,
    )
    inventory_service = SourceInventoryService(
        settings=settings,
        database=database,
        lurio_client=lurio_client,
        sensor_client=sensor_client,
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

    # Exécute un test de collecte OGO une seule fois après l'inventaire.
    ogo_client = OgoApiClient(
        base_url=settings.ogo.base_url,
        username=settings.ogo.username,
        api_key=settings.ogo.api_key,
        site_name_or_id=settings.ogo.site_name_or_id,
        timeout_seconds=settings.http_timeout_seconds,
    )
    ogo_collection_service = OgoAttackCollectionService(
        settings=settings,
        database=database,
        ogo_client=ogo_client,
    )

    try:
        ogo_result = ogo_collection_service.collect_once()
    except Exception as exc:
        LOGGER.error("Échec du test de collecte OGO : %s", exc)
        return 1

    LOGGER.info(
        "Test de collecte OGO exécuté. source=%s after=%s before=%s pages=%s lus=%s inserees=%s ignorees=%s",
        ogo_result.source_external_id,
        ogo_result.after.isoformat(),
        ogo_result.before.isoformat(),
        ogo_result.pages_read,
        ogo_result.events_read,
        ogo_result.events_inserted,
        ogo_result.events_ignored,
    )

    # Exécute un test de collecte Detoxio une seule fois après l'inventaire.
    detoxio_collection_service = SerenicitySensorAttackCollectionService(
        settings=settings,
        database=database,
        sensor_client=sensor_client,
    )
    try:
        detoxio_result = detoxio_collection_service.collect_once()
    except Exception as exc:
        LOGGER.error("Échec du test de collecte Detoxio : %s", exc)
        return 1

    LOGGER.info(
        "Test de collecte Detoxio exécuté. sources=%s succes=%s erreurs=%s pages=%s lus=%s inserees=%s ignorees=%s",
        detoxio_result.sources_selected,
        detoxio_result.sources_succeeded,
        detoxio_result.source_errors,
        detoxio_result.pages_read,
        detoxio_result.fluxes_read,
        detoxio_result.attacks_inserted,
        detoxio_result.attacks_ignored,
    )

    # Exécute un test de collecte Lurio une seule fois après l'inventaire.
    lurio_collection_service = LurioAttackCollectionService(
        settings=settings,
        database=database,
        lurio_client=lurio_client,
    )
    try:
        lurio_result = lurio_collection_service.collect_once()
    except Exception as exc:
        LOGGER.error("Échec du test de collecte Lurio : %s", exc)
        return 1

    LOGGER.info(
        "Test de collecte Lurio exécuté. sources=%s succes=%s erreurs=%s pages=%s lus=%s inserees=%s ignorees=%s",
        lurio_result.sources_selected,
        lurio_result.sources_succeeded,
        lurio_result.source_errors,
        lurio_result.pages_read,
        lurio_result.reports_read,
        lurio_result.attacks_inserted,
        lurio_result.attacks_ignored,
    )
    LOGGER.info("Fin du scheduler après inventaire, test OGO, test Detoxio et test Lurio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
