"""Orchestration du scheduler : startup initial puis boucle périodique."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import math
import time

from cyber_dashboard_scheduler.config import Settings
from cyber_dashboard_scheduler.db import PostgresDatabase
from cyber_dashboard_scheduler.repositories import SensorTypeRepository

from .inventory import SourceInventoryService
from .lurio_collection import LurioAttackCollectionService
from .ogo_collection import OgoAttackCollectionService
from .serenicity_sensor_collection import SerenicitySensorAttackCollectionService


LOGGER = logging.getLogger(__name__)


class SchedulerRuntimeService:
    """Assemble le démarrage du scheduler puis sa boucle périodique."""

    def __init__(
        self,
        *,
        settings: Settings,
        database: PostgresDatabase,
        inventory_service: SourceInventoryService,
        ogo_collection_service: OgoAttackCollectionService,
        sensor_collection_service: SerenicitySensorAttackCollectionService,
        lurio_collection_service: LurioAttackCollectionService,
    ) -> None:
        self._settings = settings
        self._database = database
        self._inventory_service = inventory_service
        self._ogo_collection_service = ogo_collection_service
        self._sensor_collection_service = sensor_collection_service
        self._lurio_collection_service = lurio_collection_service
        self._poll_interval_seconds = max(
            1,
            math.ceil(86400 / self._settings.limit_request_per_day),
        )

    def run_forever(self) -> None:
        """Exécute le démarrage complet puis la boucle infinie de collecte."""
        self._startup()

        cycle_number = 1
        while True:
            self._run_collection_cycle(cycle_number)
            cycle_number += 1
            LOGGER.info(
                "Attente de %s secondes avant le prochain cycle",
                self._poll_interval_seconds,
            )
            time.sleep(self._poll_interval_seconds)

    def _startup(self) -> None:
        """Effectue le bootstrap nécessaire avant d'entrer en boucle."""
        self._database.check_connection()

        sensor_types = self._load_sensor_types()
        LOGGER.info(
            "Types de capteurs chargés : %s",
            ", ".join(sensor_types) or "aucun",
        )
        LOGGER.info(
            "Boucle périodique configurée à un cycle toutes les %s secondes",
            self._poll_interval_seconds,
        )

        inventory_result = self._inventory_service.run_once()
        LOGGER.info(
            "Inventaire initial terminé. endpoints=%s persistes=%s desactivees=%s ignorees=%s erreurs=%s",
            ", ".join(inventory_result.endpoints_called) or "aucun",
            inventory_result.sources_persisted,
            inventory_result.sources_deactivated,
            inventory_result.sources_skipped,
            inventory_result.source_errors,
        )

    def _load_sensor_types(self) -> list[str]:
        """Charge les codes de types de capteurs au démarrage."""
        with self._database.connection() as connection:
            repository = SensorTypeRepository(connection)
            return [sensor_type.code for sensor_type in repository.list_all()]

    def _run_collection_cycle(self, cycle_number: int) -> None:
        """Lance un cycle de collecte complet en isolant les erreurs par collecteur."""
        started_at = datetime.now(UTC)
        LOGGER.info(
            "Début du cycle de collecte #%s à %s",
            cycle_number,
            started_at.isoformat(),
        )

        collectors_succeeded = 0
        collectors_failed = 0

        for collector_name, collector in (
            ("OGO", self._ogo_collection_service.collect_once),
            ("Detoxio", self._sensor_collection_service.collect_once),
            ("Lurio", self._lurio_collection_service.collect_once),
        ):
            try:
                collector()
                collectors_succeeded += 1
            except Exception as exc:
                collectors_failed += 1
                LOGGER.error(
                    "Échec du collecteur %s pendant le cycle #%s : %s",
                    collector_name,
                    cycle_number,
                    exc,
                )

        ended_at = datetime.now(UTC)
        LOGGER.info(
            "Fin du cycle de collecte #%s à %s. collecteurs_ok=%s collecteurs_en_erreur=%s duree=%.2fs",
            cycle_number,
            ended_at.isoformat(),
            collectors_succeeded,
            collectors_failed,
            (ended_at - started_at).total_seconds(),
        )
