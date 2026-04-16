"""Modèles liés à la table sources."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Source:
    """Représente une source normalisée dans le format interne du scheduler."""

    sensor_type_code: str
    external_id: str
    name: str
    latitude: float | None
    longitude: float | None
    is_active: bool
