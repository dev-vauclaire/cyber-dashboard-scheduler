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
    SchedulerRuntimeService,
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
    ogo_client = OgoApiClient(
        base_url=settings.ogo.base_url,
        username=settings.ogo.username,
        api_key=settings.ogo.api_key,
        site_name_or_id=settings.ogo.site_name_or_id,
        timeout_seconds=settings.http_timeout_seconds,
    )

    runtime_service = SchedulerRuntimeService(
        settings=settings,
        database=database,
        inventory_service=SourceInventoryService(
            settings=settings,
            database=database,
            lurio_client=lurio_client,
            sensor_client=sensor_client,
        ),
        ogo_collection_service=OgoAttackCollectionService(
            settings=settings,
            database=database,
            ogo_client=ogo_client,
        ),
        sensor_collection_service=SerenicitySensorAttackCollectionService(
            settings=settings,
            database=database,
            sensor_client=sensor_client,
        ),
        lurio_collection_service=LurioAttackCollectionService(
            settings=settings,
            database=database,
            lurio_client=lurio_client,
        ),
    )

    try:
        runtime_service.run_forever()
    except KeyboardInterrupt:
        LOGGER.info("Arrêt du scheduler demandé par l'utilisateur")
        return 0
    except Exception as exc:
        LOGGER.error("Échec du scheduler : %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
