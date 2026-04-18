"""Aides partagées pour les collectes d'attaques."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from cyber_dashboard_scheduler.models import SchedulerState, Source
from cyber_dashboard_scheduler.repositories import SchedulerStateRepository


@dataclass(frozen=True, slots=True)
class CollectionWindow:
    """Fenêtre temporelle UTC utilisée pour interroger une source.

    Attributes:
        after: Borne basse incluse de la collecte.
        before: Borne haute de la collecte.
    """

    after: datetime
    before: datetime


class CollectionResultMetrics(Protocol):
    """Contrat minimal pour agréger les métriques d'un collecteur."""

    attacks_inserted: int
    attacks_ignored: int


def build_collection_window(
    *,
    before: datetime,
    current_state: SchedulerState | None,
    safety_window_seconds: int,
) -> CollectionWindow:
    """Construit la fenêtre de collecte à partir de ``last_poll_at``.

    Args:
        before: Instant de fin du cycle en cours.
        current_state: État de collecte actuellement connu pour la source.
        safety_window_seconds: Marge de sécurité à retrancher au point de départ.

    Returns:
        Une fenêtre UTC cohérente où ``after`` reste strictement antérieur à
        ``before``.
    """
    safety_window = timedelta(seconds=safety_window_seconds)
    base_after = (
        current_state.last_poll_at
        if current_state and current_state.last_poll_at is not None
        else before - timedelta(hours=24)
    )
    after = base_after - safety_window
    if after >= before:
        after = before - timedelta(seconds=1)
    return CollectionWindow(after=after, before=before)


def persist_collection_success(
    scheduler_state_repository: SchedulerStateRepository,
    *,
    source: Source,
    current_state: SchedulerState | None,
    before: datetime,
    success_timestamp: datetime,
) -> None:
    """Enregistre un succès de collecte dans ``scheduler_state``.

    Args:
        scheduler_state_repository: Repository utilisé pour l'upsert d'état.
        source: Source collectée.
        current_state: État existant de la source, s'il existe.
        before: Fin de fenêtre collectée, stockée dans ``last_poll_at``.
        success_timestamp: Instant UTC du succès.
    """
    scheduler_state_repository.upsert(
        source,
        last_inventory_at=current_state.last_inventory_at if current_state else None,
        last_poll_at=before,
        last_success_at=success_timestamp,
        last_error_at=None,
        last_error_message=None,
    )


def persist_collection_error(
    scheduler_state_repository: SchedulerStateRepository,
    *,
    source: Source,
    current_state: SchedulerState | None,
    error: Exception,
    error_timestamp: datetime | None = None,
) -> None:
    """Enregistre un échec de collecte dans ``scheduler_state``.

    Args:
        scheduler_state_repository: Repository utilisé pour l'upsert d'état.
        source: Source en erreur.
        current_state: État existant de la source, s'il existe.
        error: Exception à conserver sous forme tronquée.
        error_timestamp: Horodatage UTC explicite, sinon l'instant courant.
    """
    scheduler_state_repository.upsert(
        source,
        last_inventory_at=current_state.last_inventory_at if current_state else None,
        last_poll_at=current_state.last_poll_at if current_state else None,
        last_success_at=current_state.last_success_at if current_state else None,
        last_error_at=error_timestamp or datetime.now(UTC),
        last_error_message=str(error)[:1000],
    )
