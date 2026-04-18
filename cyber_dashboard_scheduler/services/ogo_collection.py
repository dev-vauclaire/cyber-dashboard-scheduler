"""Collecte mono-source des attaques depuis le journal OGO."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging

from cyber_dashboard_scheduler.clients import OgoApiClient
from cyber_dashboard_scheduler.config import Settings
from cyber_dashboard_scheduler.db import PostgresDatabase
from cyber_dashboard_scheduler.models import SchedulerState, Source
from cyber_dashboard_scheduler.repositories import (
    AttackRepository,
    SchedulerStateRepository,
    SourceRepository,
)
from cyber_dashboard_scheduler.services.attack_normalization import normalize_ogo_attack
from cyber_dashboard_scheduler.services.collection_common import (
    build_collection_window,
    persist_collection_error,
    persist_collection_success,
)
from cyber_dashboard_scheduler.utils import NormalizationError


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OgoAttackCollectionResult:
    """Résumé d'une collecte d'attaques OGO."""

    source_external_id: str
    after: datetime
    before: datetime
    pages_read: int
    events_read: int
    events_inserted: int
    events_ignored: int


class OgoAttackCollectionService:
    """Collecte les attaques OGO pour la source WAF configurée."""

    def __init__(
        self,
        *,
        settings: Settings,
        database: PostgresDatabase,
        ogo_client: OgoApiClient,
    ) -> None:
        """Construit le service de collecte OGO.

        Args:
            settings: Configuration applicative du scheduler.
            database: Accès PostgreSQL.
            ogo_client: Client HTTP OGO.
        """
        self._settings = settings
        self._database = database
        self._ogo_client = ogo_client

    def collect_once(self) -> OgoAttackCollectionResult:
        """Collecte les attaques OGO pour la source WAF active configurée.

        Returns:
            Le résumé de la collecte OGO.

        Raises:
            Exception: Relance toute erreur après mise à jour de ``scheduler_state``.
        """
        source = self._load_active_ogo_source()
        current_state = self._load_scheduler_state(source)
        collection_window = build_collection_window(
            before=datetime.now(UTC),
            current_state=current_state,
            safety_window_seconds=self._settings.poll_safety_window_seconds,
        )

        LOGGER.info(
            "Collecte OGO démarrée source=%s after=%s before=%s",
            source.external_id,
            collection_window.after.isoformat(),
            collection_window.before.isoformat(),
        )

        try:
            fetch_result = self._ogo_client.list_security_events(
                after=collection_window.after,
                before=collection_window.before,
            )
            result = self._persist_attacks(
                source=source,
                current_state=current_state,
                after=collection_window.after,
                before=collection_window.before,
                pages_read=fetch_result.pages_read,
                payloads=fetch_result.items,
            )
        except Exception as exc:
            self._record_collection_error(source=source, current_state=current_state, error=exc)
            LOGGER.exception(
                "Collecte OGO en erreur source=%s: %s",
                source.external_id,
                exc,
            )
            raise
       
        LOGGER.info(
            "Collecte OGO terminée source=%s pages=%s lus=%s inserees=%s ignorees=%s",
            result.source_external_id,
            result.pages_read,
            result.events_read,
            result.events_inserted,
            result.events_ignored,
        )
        return result
    

    def _load_active_ogo_source(self) -> Source:
        """Charge l'unique source OGO/WAF active configurée.

        Returns:
            La source OGO active.

        Raises:
            RuntimeError: Si la source attendue n'est pas présente en base.
        """
        with self._database.connection() as connection:
            source_repository = SourceRepository(connection)
            active_sources = source_repository.list_active()

        expected_external_id = self._settings.ogo.site_name_or_id
        for source in active_sources:
            if source.sensor_type_code == "waf" and source.external_id == expected_external_id:
                return source

        raise RuntimeError(
            "Source OGO/WAF active introuvable en base pour la collecte : "
            f"waf/{expected_external_id}"
        )

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
        after: datetime,
        before: datetime,
        pages_read: int,
        payloads: list[dict],
    ) -> OgoAttackCollectionResult:
        """Normalise puis insère les attaques OGO avant d'enregistrer le succès.

        Args:
            source: Source OGO collectée.
            current_state: État courant de la source.
            after: Borne basse collectée.
            before: Borne haute collectée.
            pages_read: Nombre de pages lues côté API.
            payloads: Événements bruts retournés par OGO.

        Returns:
            Le résumé de persistance de la collecte.
        """
        events_inserted = 0
        events_ignored = 0
        success_timestamp = datetime.now(UTC)

        with self._database.transaction() as connection:
            attack_repository = AttackRepository(connection)
            scheduler_state_repository = SchedulerStateRepository(connection)

            for payload in payloads:
                try:
                    attack = normalize_ogo_attack(
                        source,
                        payload,
                        collected_at=success_timestamp,
                    )
                except NormalizationError as exc:
                    events_ignored += 1
                    LOGGER.warning(
                        "Attaque OGO ignorée source=%s raison=%s",
                        source.external_id,
                        exc,
                    )
                    continue

                if attack is None:
                    events_ignored += 1
                    continue

                if attack_repository.insert(attack):
                    events_inserted += 1
                else:
                    events_ignored += 1

            persist_collection_success(
                scheduler_state_repository,
                source=source,
                current_state=current_state,
                before=before,
                success_timestamp=success_timestamp,
            )

        return OgoAttackCollectionResult(
            source_external_id=source.external_id,
            after=after,
            before=before,
            pages_read=pages_read,
            events_read=len(payloads),
            events_inserted=events_inserted,
            events_ignored=events_ignored,
        )

    def _record_collection_error(
        self,
        *,
        source: Source,
        current_state: SchedulerState | None,
        error: Exception,
    ) -> None:
        """Persistе un échec de collecte OGO dans ``scheduler_state``.

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
                "Impossible de mettre à jour scheduler_state en erreur pour la collecte OGO %s/%s : %s",
                source.sensor_type_code,
                source.external_id,
                exc,
            )
