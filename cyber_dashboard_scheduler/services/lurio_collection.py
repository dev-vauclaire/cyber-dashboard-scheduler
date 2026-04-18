"""Collecte des attaques depuis les lurios Serenicity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging

from cyber_dashboard_scheduler.clients import SerenicityLurioClient
from cyber_dashboard_scheduler.config import Settings
from cyber_dashboard_scheduler.db import PostgresDatabase
from cyber_dashboard_scheduler.models import SchedulerState, Source
from cyber_dashboard_scheduler.repositories import (
    AttackRepository,
    SchedulerStateRepository,
    SourceRepository,
)
from cyber_dashboard_scheduler.services.collection_common import (
    build_collection_window,
    persist_collection_error,
    persist_collection_success,
)
from cyber_dashboard_scheduler.services.attack_normalization import normalize_lurio_report
from cyber_dashboard_scheduler.utils import NormalizationError


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LurioAttackCollectionResult:
    """Résumé agrégé d'une collecte Lurio."""

    sources_selected: int
    sources_succeeded: int
    source_errors: int
    pages_read: int
    reports_read: int
    attacks_inserted: int
    attacks_ignored: int


class LurioAttackCollectionService:
    """Collecte les attaques depuis les sources actives de type lurio."""

    def __init__(
        self,
        *,
        settings: Settings,
        database: PostgresDatabase,
        lurio_client: SerenicityLurioClient,
    ) -> None:
        """Construit le service de collecte Lurio.

        Args:
            settings: Configuration applicative du scheduler.
            database: Accès PostgreSQL.
            lurio_client: Client HTTP Serenicity pour les lurios.
        """
        self._settings = settings
        self._database = database
        self._lurio_client = lurio_client

    def collect_once(self) -> LurioAttackCollectionResult:
        """Collecte une fois les reports Lurio pour toutes les sources actives.

        Returns:
            Le résumé agrégé de cette collecte Lurio.
        """
        sources = self._load_active_lurio_sources()
        if not sources:
            LOGGER.info("Aucune source lurio active à collecter")
            return LurioAttackCollectionResult(
                sources_selected=0,
                sources_succeeded=0,
                source_errors=0,
                pages_read=0,
                reports_read=0,
                attacks_inserted=0,
                attacks_ignored=0,
            )

        sources_succeeded = 0
        source_errors = 0
        pages_read = 0
        reports_read = 0
        attacks_inserted = 0
        attacks_ignored = 0

        for source in sources:
            current_state = self._load_scheduler_state(source)
            collection_window = build_collection_window(
                before=datetime.now(UTC),
                current_state=current_state,
                safety_window_seconds=self._settings.poll_safety_window_seconds,
            )

            LOGGER.info(
                "Collecte Lurio démarrée source=%s from=%s to=%s",
                source.external_id,
                collection_window.after.isoformat(),
                collection_window.before.isoformat(),
            )

            try:
                fetch_result = self._lurio_client.list_lurio_reports(
                    lurio_id=source.external_id,
                    from_datetime=collection_window.after,
                    to_datetime=collection_window.before,
                )
                source_inserted, source_ignored = self._persist_attacks(
                    source=source,
                    current_state=current_state,
                    before=collection_window.before,
                    payloads=fetch_result.items,
                )
            except Exception as exc:
                source_errors += 1
                self._record_collection_error(
                    source=source,
                    current_state=current_state,
                    error=exc,
                )
                LOGGER.exception(
                    "Collecte Lurio en erreur source=%s: %s",
                    source.external_id,
                    exc,
                )
                continue

            sources_succeeded += 1
            pages_read += fetch_result.pages_read
            reports_read += len(fetch_result.items)
            attacks_inserted += source_inserted
            attacks_ignored += source_ignored

            LOGGER.info(
                "Collecte Lurio terminée source=%s pages=%s lus=%s inserees=%s ignorees=%s",
                source.external_id,
                fetch_result.pages_read,
                len(fetch_result.items),
                source_inserted,
                source_ignored,
            )

        result = LurioAttackCollectionResult(
            sources_selected=len(sources),
            sources_succeeded=sources_succeeded,
            source_errors=source_errors,
            pages_read=pages_read,
            reports_read=reports_read,
            attacks_inserted=attacks_inserted,
            attacks_ignored=attacks_ignored,
        )
        LOGGER.info(
            "Collecte Lurio terminée sources=%s succes=%s erreurs=%s pages=%s lus=%s inserees=%s ignorees=%s",
            result.sources_selected,
            result.sources_succeeded,
            result.source_errors,
            result.pages_read,
            result.reports_read,
            result.attacks_inserted,
            result.attacks_ignored,
        )
        return result

    def _load_active_lurio_sources(self) -> list[Source]:
        """Charge les sources actives compatibles avec la collecte Lurio.

        Returns:
            La liste des sources ``lurio`` actives.
        """
        with self._database.connection() as connection:
            source_repository = SourceRepository(connection)
            active_sources = source_repository.list_active()

        return [source for source in active_sources if source.sensor_type_code == "lurio"]

    def _load_scheduler_state(self, source: Source) -> SchedulerState | None:
        """Charge l'état courant du scheduler pour une source.

        Args:
            source: Source dont il faut lire l'état.

        Returns:
            L'état courant ou ``None``.
        """
        with self._database.connection() as connection:
            scheduler_state_repository = SchedulerStateRepository(connection)
            return scheduler_state_repository.get_by_source(source)

    def _persist_attacks(
        self,
        *,
        source: Source,
        current_state: SchedulerState | None,
        before: datetime,
        payloads: list[dict[str, object]],
    ) -> tuple[int, int]:
        """Normalise puis insère les reports Lurio d'une source.

        Args:
            source: Source collectée.
            current_state: État courant de la source.
            before: Fin de fenêtre collectée à mémoriser.
            payloads: Reports bruts renvoyés par l'API.

        Returns:
            Un tuple ``(insérées, ignorées)``.
        """
        success_timestamp = datetime.now(UTC)
        attacks_inserted = 0
        attacks_ignored = 0

        with self._database.transaction() as connection:
            attack_repository = AttackRepository(connection)
            scheduler_state_repository = SchedulerStateRepository(connection)

            for payload in payloads:
                try:
                    attack = normalize_lurio_report(
                        source,
                        payload,
                        collected_at=success_timestamp,
                    )
                except NormalizationError as exc:
                    attacks_ignored += 1
                    LOGGER.warning(
                        "Report Lurio ignoré source=%s raison=%s",
                        source.external_id,
                        exc,
                    )
                    continue

                if attack is None:
                    attacks_ignored += 1
                    continue

                if attack_repository.insert(attack):
                    attacks_inserted += 1
                else:
                    attacks_ignored += 1

            persist_collection_success(
                scheduler_state_repository,
                source=source,
                current_state=current_state,
                before=before,
                success_timestamp=success_timestamp,
            )

        return attacks_inserted, attacks_ignored

    def _record_collection_error(
        self,
        *,
        source: Source,
        current_state: SchedulerState | None,
        error: Exception,
    ) -> None:
        """Persistе un échec de collecte Lurio dans ``scheduler_state``.

        Args:
            source: Source en erreur.
            current_state: État courant connu.
            error: Exception à historiser.
        """
        try:
            with self._database.transaction() as connection:
                scheduler_state_repository = SchedulerStateRepository(connection)
                persist_collection_error(
                    scheduler_state_repository,
                    source=source,
                    current_state=current_state,
                    error=error,
                )
        except Exception as exc:
            LOGGER.warning(
                "Impossible de mettre à jour scheduler_state en erreur pour la collecte Lurio %s/%s : %s",
                source.sensor_type_code,
                source.external_id,
                exc,
            )
