"""Normalisation des sources externes vers le format interne."""

from __future__ import annotations

from typing import Any, Mapping

from cyber_dashboard_scheduler.models import Source
from cyber_dashboard_scheduler.utils.normalization import (
    require_identifier,
    require_text,
    optional_float,
)


def normalize_ogo_waf_source(site_name_or_id: str) -> Source:
    """Normalise la source OGO/WAF configurée côté scheduler."""
    site_value = require_text(site_name_or_id, "site_name_or_id")
    return Source(
        sensor_type_code="waf",
        external_id=site_value,
        name="OGO/WAF",
        latitude=None,
        longitude=None,
        is_active=True,
    )


def normalize_serenicity_sensor(payload: Mapping[str, Any]) -> Source:
    """Normalise une source Serenicity vers le format interne."""
    sensor_id = require_identifier(payload.get("id"), "id")
    sensor_type_code = require_text(payload.get("type_fk"), "type_fk").lower()
    name = require_text(payload.get("full_name"), "full_name")
    status = require_text(payload.get("status"), "status").upper()

    return Source(
        sensor_type_code=sensor_type_code,
        external_id=sensor_id,
        name=name,
        latitude=optional_float(payload.get("latitude"), "latitude", -90.0, 90.0),
        longitude=optional_float(payload.get("longitude"), "longitude", -180.0, 180.0),
        is_active=status == "CONNECTED",
    )


def normalize_lurio_source(payload: Mapping[str, Any]) -> Source:
    """Normalise une source Lurio vers le format interne."""
    lurio_id = require_identifier(payload.get("id"), "id")
    name = require_text(payload.get("name"), "name")
    status = require_text(payload.get("status"), "status").upper()

    return Source(
        sensor_type_code="lurio",
        external_id=lurio_id,
        name=name,
        latitude=optional_float(payload.get("latitude"), "latitude", -90.0, 90.0),
        longitude=optional_float(payload.get("longitude"), "longitude", -180.0, 180.0),
        is_active=status == "CONNECTED",
    )
