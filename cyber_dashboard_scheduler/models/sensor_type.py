"""Modèles liés à la table sensor_types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SensorType:
    """Représente une ligne de la table sensor_types."""

    id: int
    code: str
    label: str
    category: str
    color: str
