"""Service d'inventaire initial des sources du scheduler."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import logging
from typing import Any, Callable, Iterable, Mapping, TypeAlias

from cyber_dashboard_scheduler.clients import ApiClientError, SerenicityApiClient
from cyber_dashboard_scheduler.config import Settings
from cyber_dashboard_scheduler.db import PostgresDatabase
from cyber_dashboard_scheduler.models import Source
from cyber_dashboard_scheduler.repositories import (
    SchedulerStateRepository,
    SensorTypeRepository,
    SourceRepository,
)
from cyber_dashboard_scheduler.services.source_normalization import (
    normalize_lurio_source,
    normalize_ogo_waf_source,
    normalize_serenicity_sensor,
)
from cyber_dashboard_scheduler.utils import NormalizationError


LOGGER = logging.getLogger(__name__)
SourceKey: TypeAlias = tuple[str, str]


@dataclass(slots=True)
class InventoryRunResult:
    """Résumé d'un inventaire de sources."""

    endpoints_called: list[str] = field(default_factory=list)
    sources_detected: int = 0
    sources_persisted: int = 0
    sources_deactivated: int = 0
    sources_skipped: int = 0
    source_errors: int = 0


class SourceInventoryService:
    """Orchestre l'inventaire des sources actives du scheduler."""

    def __init__(
        self,
        *,
        settings: Settings,
        database: PostgresDatabase,
        serenicity_client: SerenicityApiClient,
    ) -> None:
        self._settings = settings
        self._database = database
        self._serenicity_client = serenicity_client

    def run_once(self) -> InventoryRunResult:
        """Exécute un inventaire complet des sources une seule fois."""
        inventory_timestamp = datetime.now(UTC)
        result = InventoryRunResult()
        supported_sensor_types = self._load_supported_sensor_type_codes()
        active_sources_before_inventory = self._load_active_sources_before_inventory(
            supported_sensor_types
        )
        seen_source_keys: set[SourceKey] = set()

        LOGGER.info(
            "Début de l'inventaire des sources. Types supportés : %s. Sources actives en base avant inventaire : %s",
            ", ".join(sorted(supported_sensor_types)) or "aucun",
            len(active_sources_before_inventory),
        )

        self._inventory_ogo_waf(
            supported_sensor_types=supported_sensor_types,
            inventory_timestamp=inventory_timestamp,
            result=result,
            seen_source_keys=seen_source_keys,
        )
        self._inventory_lurios(
            supported_sensor_types=supported_sensor_types,
            inventory_timestamp=inventory_timestamp,
            result=result,
            seen_source_keys=seen_source_keys,
        )
        self._inventory_sensors(
            supported_sensor_types=supported_sensor_types,
            inventory_timestamp=inventory_timestamp,
            result=result,
            seen_source_keys=seen_source_keys,
        )
        self._deactivate_missing_sources(
            active_sources_before_inventory=active_sources_before_inventory,
            seen_source_keys=seen_source_keys,
            inventory_timestamp=inventory_timestamp,
            result=result,
        )

        LOGGER.info(
            "Inventaire terminé. detectees=%s persistes=%s desactivees=%s ignorees=%s erreurs=%s",
            result.sources_detected,
            result.sources_persisted,
            result.sources_deactivated,
            result.sources_skipped,
            result.source_errors,
        )
        return result

    def _load_supported_sensor_type_codes(self) -> set[str]:
        with self._database.connection() as connection:
            repository = SensorTypeRepository(connection)
            return {sensor_type.code for sensor_type in repository.list_all()}

    def _load_active_sources_before_inventory(
        self,
        supported_sensor_types: set[str],
    ) -> dict[SourceKey, Source]:
        """Charge les sources actives déjà présentes en base avant l'inventaire."""
        with self._database.connection() as connection:
            repository = SourceRepository(connection)
            sources = repository.list_active()

        active_sources = {
            _build_source_key(source): source
            for source in sources
            if source.sensor_type_code in supported_sensor_types
        }
        LOGGER.info(
            "%s sources actives existantes ont été chargées avant inventaire",
            len(active_sources),
        )
        return active_sources

    def _inventory_ogo_waf(
        self,
        *,
        supported_sensor_types: set[str],
        inventory_timestamp: datetime,
        result: InventoryRunResult,
        seen_source_keys: set[SourceKey],
    ) -> None:
        if "waf" not in supported_sensor_types:
            LOGGER.info("Type waf absent de sensor_types, source OGO/WAF ignorée")
            return

        LOGGER.info("Création de la source OGO/WAF à partir de la configuration locale")
        source = normalize_ogo_waf_source(self._settings.ogo.site_name_or_id)
        result.endpoints_called.append("local:ogo_waf")
        result.sources_detected += 1
        seen_source_keys.add(_build_source_key(source))
        self._persist_source(
            source=source,
            inventory_timestamp=inventory_timestamp,
            result=result,
            origin="OGO/WAF",
        )

    def _inventory_lurios(
        self,
        *,
        supported_sensor_types: set[str],
        inventory_timestamp: datetime,
        result: InventoryRunResult,
        seen_source_keys: set[SourceKey],
    ) -> None:
        if "lurio" not in supported_sensor_types:
            LOGGER.info("Type lurio absent de sensor_types, appel /api/v1/lurios ignoré")
            return

        endpoint = "GET /api/v1/lurios"
        result.endpoints_called.append(endpoint)
        try:
            payloads = self._serenicity_client.list_lurios()
        except ApiClientError as exc:
            result.source_errors += 1
            LOGGER.error("Échec de l'inventaire Lurio via %s : %s", endpoint, exc)
            return

        LOGGER.info("%s lurios récupérés depuis Serenicity", len(payloads))
        self._process_payloads(
            payloads=payloads,
            normalizer=normalize_lurio_source,
            supported_sensor_types=supported_sensor_types,
            inventory_timestamp=inventory_timestamp,
            result=result,
            origin="Lurio",
            seen_source_keys=seen_source_keys,
        )

    def _inventory_sensors(
        self,
        *,
        supported_sensor_types: set[str],
        inventory_timestamp: datetime,
        result: InventoryRunResult,
        seen_source_keys: set[SourceKey],
    ) -> None:
        if not supported_sensor_types or "detoxio" not in supported_sensor_types:
            LOGGER.info("Aucun type Serenicity supporté dans sensor_types, appel /api/v1/sensors ignoré")
            return

        endpoint = "GET /api/v1/sensors"
        result.endpoints_called.append(endpoint)
        try:
            payloads = self._serenicity_client.list_sensors()
        except ApiClientError as exc:
            result.source_errors += 1
            LOGGER.error("Échec de l'inventaire Serenicity via %s : %s", endpoint, exc)
            return

        LOGGER.info("%s capteurs Serenicity récupérés", len(payloads))
        self._process_payloads(
            payloads=payloads,
            normalizer=normalize_serenicity_sensor,
            supported_sensor_types=supported_sensor_types,
            inventory_timestamp=inventory_timestamp,
            result=result,
            origin="Serenicity",
            seen_source_keys=seen_source_keys,
        )

    def _process_payloads(
        self,
        *,
        payloads: Iterable[Mapping[str, Any]],
        normalizer: Callable[[Mapping[str, Any]], Source],
        supported_sensor_types: set[str],
        inventory_timestamp: datetime,
        result: InventoryRunResult,
        origin: str,
        seen_source_keys: set[SourceKey],
    ) -> None:
        for payload in payloads:
            result.sources_detected += 1
            try:
                source = normalizer(payload)
            except NormalizationError as exc:
                result.sources_skipped += 1
                LOGGER.warning("Source %s ignorée car invalide : %s", origin, exc)
                continue

            if source.sensor_type_code not in supported_sensor_types:
                result.sources_skipped += 1
                LOGGER.info(
                    "Source %s ignorée car type non supporté : %s/%s",
                    origin,
                    source.sensor_type_code,
                    source.external_id,
                )
                continue

            if not source.is_active:
                result.sources_skipped += 1
                LOGGER.info(
                    "Source %s ignorée car inactive : %s/%s",
                    origin,
                    source.sensor_type_code,
                    source.external_id,
                )
                continue

            seen_source_keys.add(_build_source_key(source))
            self._persist_source(
                source=source,
                inventory_timestamp=inventory_timestamp,
                result=result,
                origin=origin,
            )

    def _persist_source(
        self,
        *,
        source: Source,
        inventory_timestamp: datetime,
        result: InventoryRunResult,
        origin: str,
    ) -> None:
        try:
            with self._database.transaction() as connection:
                source_repository = SourceRepository(connection)
                scheduler_state_repository = SchedulerStateRepository(connection)

                persisted_source = source_repository.upsert(source)
                current_state = scheduler_state_repository.get_by_source(persisted_source)
                scheduler_state_repository.upsert(
                    persisted_source,
                    last_inventory_at=inventory_timestamp,
                    last_poll_at=current_state.last_poll_at if current_state else None,
                    last_success_at=inventory_timestamp,
                    last_error_at=None,
                    last_error_message=None,
                )
        except Exception as exc:
            result.source_errors += 1
            LOGGER.error(
                "Échec de l'inventaire pour la source %s %s/%s : %s",
                origin,
                source.sensor_type_code,
                source.external_id,
                exc,
            )
            self._record_inventory_error(
                source=source,
                inventory_timestamp=inventory_timestamp,
                error_message=str(exc),
            )
            return

        result.sources_persisted += 1
        LOGGER.info(
            "Source inventoriée avec succès : %s/%s",
            persisted_source.sensor_type_code,
            persisted_source.external_id,
        )

    def _deactivate_missing_sources(
        self,
        *,
        active_sources_before_inventory: dict[SourceKey, Source],
        seen_source_keys: set[SourceKey],
        inventory_timestamp: datetime,
        result: InventoryRunResult,
    ) -> None:
        missing_sources = [
            source
            for source_key, source in active_sources_before_inventory.items()
            if source_key not in seen_source_keys
        ]
        if not missing_sources:
            LOGGER.info("Aucune source active à désactiver après inventaire")
            return

        LOGGER.info(
            "%s sources actives n'ont pas été revues pendant l'inventaire et vont être désactivées",
            len(missing_sources),
        )
        for source in missing_sources:
            inactive_source = Source(
                sensor_type_code=source.sensor_type_code,
                external_id=source.external_id,
                name=source.name,
                latitude=source.latitude,
                longitude=source.longitude,
                is_active=False,
            )
            try:
                with self._database.transaction() as connection:
                    source_repository = SourceRepository(connection)
                    scheduler_state_repository = SchedulerStateRepository(connection)

                    persisted_source = source_repository.upsert(inactive_source)
                    current_state = scheduler_state_repository.get_by_source(persisted_source)
                    scheduler_state_repository.upsert(
                        persisted_source,
                        last_inventory_at=inventory_timestamp,
                        last_poll_at=current_state.last_poll_at if current_state else None,
                        last_success_at=inventory_timestamp,
                        last_error_at=None,
                        last_error_message=None,
                    )
            except Exception as exc:
                result.source_errors += 1
                LOGGER.error(
                    "Échec de la désactivation de la source absente de l'inventaire %s/%s : %s",
                    inactive_source.sensor_type_code,
                    inactive_source.external_id,
                    exc,
                )
                self._record_inventory_error(
                    source=inactive_source,
                    inventory_timestamp=inventory_timestamp,
                    error_message=str(exc),
                )
                continue

            result.sources_deactivated += 1
            LOGGER.info(
                "Source désactivée car absente de l'inventaire : %s/%s",
                persisted_source.sensor_type_code,
                persisted_source.external_id,
            )

    def _record_inventory_error(
        self,
        *,
        source: Source,
        inventory_timestamp: datetime,
        error_message: str,
    ) -> None:
        try:
            with self._database.transaction() as connection:
                scheduler_state_repository = SchedulerStateRepository(connection)
                current_state = scheduler_state_repository.get_by_source(source)
                if current_state is None:
                    return

                scheduler_state_repository.upsert(
                    source,
                    last_inventory_at=inventory_timestamp,
                    last_poll_at=current_state.last_poll_at,
                    last_success_at=current_state.last_success_at,
                    last_error_at=inventory_timestamp,
                    last_error_message=error_message[:1000],
                )
        except Exception as exc:
            LOGGER.warning(
                "Impossible de mettre à jour scheduler_state en erreur pour %s/%s : %s",
                source.sensor_type_code,
                source.external_id,
                exc,
            )


def _build_source_key(source: Source) -> SourceKey:
    """Construit une clé stable pour comparer les sources d'un run à l'autre."""
    return (source.sensor_type_code, source.external_id)
