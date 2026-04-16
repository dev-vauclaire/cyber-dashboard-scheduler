"""Modèles liés à la table scheduler_state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SchedulerState:
    """Représente une ligne de la table scheduler_state."""

    source_id: int
    last_inventory_at: datetime | None
    last_poll_at: datetime | None
    last_success_at: datetime | None
    last_error_at: datetime | None
    last_error_message: str | None
