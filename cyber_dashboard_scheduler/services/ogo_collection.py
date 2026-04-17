"""Collecte mono-source des attaques depuis le journal OGO."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
        self._settings = settings
        self._database = database
        self._ogo_client = ogo_client

    def collect_once(self) -> OgoAttackCollectionResult:
        """Collecte les attaques OGO pour la source WAF active configurée."""
        
        # Récupère la source OGO/WAF active et l'état de collecte actuel en base
        source = self._load_active_ogo_source()
        current_state = self._load_scheduler_state(source)

        before = datetime.now(UTC)
        after = self._compute_after(before=before, current_state=current_state)

        LOGGER.info(
            "Début de la collecte OGO pour %s. Fenêtre after=%s before=%s",
            source.external_id,
            after.isoformat(),
            before.isoformat(),
        )

        try:
            fetch_result = self._ogo_client.list_security_events(
                after=after,
                before=before,
            )
            result = self._persist_attacks(
                source=source,
                current_state=current_state,
                after=after,
                before=before,
                pages_read=fetch_result.pages_read,
                payloads=fetch_result.items,
            )
        except Exception as exc:
            self._record_collection_error(source=source, current_state=current_state, error=exc)
            LOGGER.error(
                "Échec de la collecte OGO pour %s : %s",
                source.external_id,
                exc,
            )
            raise
       
        LOGGER.info(
            "Collecte OGO terminée pour %s. lus=%s inserees=%s ignorees=%s pages=%s",
            result.source_external_id,
            result.events_read,
            result.events_inserted,
            result.events_ignored,
            result.pages_read,
        )
        return result
    

    def _load_active_ogo_source(self) -> Source:
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
        with self._database.connection() as connection:
            scheduler_state_repository = SchedulerStateRepository(connection)
            return scheduler_state_repository.get_by_source(source)

    def _compute_after(
        self,
        *,
        before: datetime,
        current_state: SchedulerState | None,
    ) -> datetime:
        """
        Calcule la borne 'after' pour la récupération des événements.
        Règles :
        - Si on a un last_poll_at → on repart de là
        - Sinon → on remonte à 24h dans le passé
        - On applique une safety window pour éviter les pertes de données
        - On garantit que 'after' reste strictement avant 'before'
        """

        safety_window = timedelta(seconds=self._settings.poll_safety_window_seconds)

        # 1. Déterminer le point de départ de base
        if current_state and current_state.last_poll_at:
            base_after = current_state.last_poll_at
        else:
            base_after = before - timedelta(hours=24)

        # 2. Appliquer la safety window (on remonte un peu dans le passé)
        after = base_after - safety_window

        # 3. Sécurité : éviter que 'after' dépasse 'before'
        if after > before:
            after = before - safety_window

        return after

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
                except NormalizationError:
                    events_ignored += 1
                    continue

                if attack is None:
                    events_ignored += 1
                    continue

                if attack_repository.insert(attack):
                    events_inserted += 1
                else:
                    events_ignored += 1

            scheduler_state_repository.upsert(
                source,
                last_inventory_at=current_state.last_inventory_at if current_state else None,
                last_poll_at=before,
                last_success_at=success_timestamp,
                last_error_at=None,
                last_error_message=None,
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
        try:
            with self._database.transaction() as connection:
                scheduler_state_repository = SchedulerStateRepository(connection)
                scheduler_state_repository.upsert(
                    source,
                    last_inventory_at=current_state.last_inventory_at if current_state else None,
                    last_poll_at=current_state.last_poll_at if current_state else None,
                    last_success_at=current_state.last_success_at if current_state else None,
                    last_error_at=datetime.now(UTC),
                    last_error_message=str(error)[:1000],
                )
        except Exception as exc:
            LOGGER.warning(
                "Impossible de mettre à jour scheduler_state en erreur pour la collecte OGO %s/%s : %s",
                source.sensor_type_code,
                source.external_id,
                exc,
            )
