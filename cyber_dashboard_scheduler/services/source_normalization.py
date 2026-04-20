"""Normalisation des sources externes vers le format interne."""

from __future__ import annotations

from typing import Any, Mapping

from cyber_dashboard_scheduler.models import Source
from cyber_dashboard_scheduler.utils import (
    NormalizationError,
    derive_color_random,
    optional_text,
    optional_float,
    require_hex_color,
    require_identifier,
    require_text,
)


def normalize_ogo_waf_source(site_name_or_id: str, sensor_type_color: str) -> Source:
    """Normalise la source OGO/WAF configurée côté scheduler."""
    site_value = require_text(site_name_or_id, "site_name_or_id")
    base_color = _derive_source_color(sensor_type_color, "waf.color")
    return Source(
        sensor_type_code="waf",
        external_id=site_value,
        name=site_value,
        latitude=None,
        longitude=None,
        is_active=True,
        color=base_color,
    )


def normalize_serenicity_sensor(
    payload: Mapping[str, Any],
    sensor_type_colors: Mapping[str, str],
) -> Source:
    """Normalise une source Serenicity vers le format interne."""
    sensor_id = require_identifier(payload.get("id"), "id")
    sensor_type_code = require_text(payload.get("type_fk"), "type_fk").lower()
    name = optional_text(payload.get("full_name")) or require_text(payload.get("name"), "name")
    status = require_text(payload.get("status"), "status").upper()
    base_color = _derive_sensor_type_color(
        sensor_type_code=sensor_type_code,
        sensor_type_colors=sensor_type_colors,
    )

    return Source(
        sensor_type_code=sensor_type_code,
        external_id=sensor_id,
        name=name,
        latitude=optional_float(payload.get("latitude"), "latitude", -90.0, 90.0),
        longitude=optional_float(payload.get("longitude"), "longitude", -180.0, 180.0),
        is_active=_is_active_status(status),
        color=base_color,
    )


def normalize_lurio_source(payload: Mapping[str, Any], sensor_type_color: str) -> Source:
    """Normalise une source Lurio vers le format interne."""
    lurio_id = require_identifier(payload.get("id"), "id")
    name = require_text(payload.get("name"), "name")
    status = require_text(payload.get("status"), "status").upper()
    base_color = _derive_source_color(sensor_type_color, "lurio.color")

    return Source(
        sensor_type_code="lurio",
        external_id=lurio_id,
        name=name,
        latitude=optional_float(payload.get("latitude"), "latitude", -90.0, 90.0),
        longitude=optional_float(payload.get("longitude"), "longitude", -180.0, 180.0),
        is_active=_is_active_status(status),
        color=base_color,
    )


def _is_active_status(status: str) -> bool:
    """Retourne ``True`` si le statut indique une source active."""
    return status in {"CONNECTED", "ACTIVE"}


def _derive_source_color(sensor_type_color: str, field_name: str) -> str:
    """Dérive une couleur de source à partir de la couleur d'un type de capteur."""
    try:
        return derive_color_random(require_hex_color(sensor_type_color, field_name))
    except ValueError as exc:
        raise NormalizationError(str(exc)) from exc


def _derive_sensor_type_color(
    *,
    sensor_type_code: str,
    sensor_type_colors: Mapping[str, str],
) -> str:
    """Récupère puis dérive la couleur d'une source à partir de son type."""
    sensor_type_color = sensor_type_colors.get(sensor_type_code)
    if sensor_type_color is None:
        raise NormalizationError(
            f"Type de capteur sans couleur configurée : {sensor_type_code}"
        )
    return _derive_source_color(sensor_type_color, f"sensor_type_colors[{sensor_type_code}]")
