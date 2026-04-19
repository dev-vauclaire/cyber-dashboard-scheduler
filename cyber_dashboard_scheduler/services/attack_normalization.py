"""Normalisation des attaques et flux externes vers le format interne."""

from __future__ import annotations

from typing import Any, Mapping

from cyber_dashboard_scheduler.models import Attack, Source
from cyber_dashboard_scheduler.utils.normalization import (
    copy_payload,
    normalize_collected_at,
    normalize_datetime_to_utc,
    optional_text,
    require_ip,
    require_mapping,
    require_text,
    to_bool,
    NormalizationError,
)


def normalize_ogo_attack(
    source: Source,
    payload: Mapping[str, Any],
    collected_at: Any = None,
) -> Attack | None:
    """Normalise une attaque OGO vers le format interne."""
    _require_source_type(source, "waf", "normalize_ogo_attack")

    site = require_text(payload.get("site"), "site")
    if site != source.external_id:
        return None

    event = require_mapping(payload.get("event"), "event")
    return Attack(
        sensor_type_code=source.sensor_type_code,
        source_external_id=source.external_id,
        source_event_id=_optional_source_event_id(payload, event),
        attacker_ip=require_ip(event.get("ip"), "event.ip"),
        occurred_at=normalize_datetime_to_utc(payload.get("date"), "date"),
        collected_at=normalize_collected_at(collected_at),
        attack_type=None,  # OGO ne fournit pas de type d'attaque structuré
        raw_payload=copy_payload(payload),
    )


def normalize_serenicity_sensor_flux(
    source: Source,
    payload: Mapping[str, Any],
    collected_at: Any = None,
) -> Attack | None:
    """Normalise un flux de capteur Serenicity vers le format interne."""
    _require_source_type(source, "detoxio", "normalize_serenicity_sensor_flux")

    if not to_bool(payload.get("toxic")):
        return None

    return Attack(
        sensor_type_code=source.sensor_type_code,
        source_external_id=source.external_id,
        source_event_id=_optional_source_event_id(payload),
        attacker_ip=require_ip(payload.get("ip1"), "ip1"),
        occurred_at=normalize_datetime_to_utc(payload.get("start_of_hour"), "start_of_hour"),
        collected_at=normalize_collected_at(collected_at),
        attack_type=optional_text(payload.get("protocol")),
        raw_payload=copy_payload(payload),
    )


def normalize_lurio_report(
    source: Source,
    payload: Mapping[str, Any],
    collected_at: Any = None,
) -> Attack | None:
    """Normalise un report Lurio vers le format interne."""
    _require_source_type(source, "lurio", "normalize_lurio_report")

    threat = payload.get("threat")
    threat_payload = threat if isinstance(threat, Mapping) else {}

    return Attack(
        sensor_type_code=source.sensor_type_code,
        source_external_id=source.external_id,
        source_event_id=_optional_source_event_id(payload, threat_payload),
        attacker_ip=require_ip(payload.get("ip"), "ip"),
        occurred_at=normalize_datetime_to_utc(payload.get("created_at"), "created_at"),
        collected_at=normalize_collected_at(collected_at),
        attack_type=optional_text(threat_payload.get("type")),
        raw_payload=copy_payload(payload),
    )


def _require_source_type(source: Source, expected_code: str, function_name: str) -> None:
    """Vérifie qu'une source correspond bien au type attendu.

    Args:
        source: Source à valider.
        expected_code: Code attendu.
        function_name: Nom de la fonction appelante pour le message d'erreur.

    Raises:
        NormalizationError: Si le type de source ne correspond pas.
    """
    if source.sensor_type_code.lower() != expected_code:
        raise NormalizationError(
            f"{function_name} attend une source de type {expected_code}, "
            f"reçu {source.sensor_type_code}"
        )


def _optional_source_event_id(*payloads: Mapping[str, Any]) -> str | None:
    """Extrait un identifiant d'événement optionnel depuis plusieurs payloads.

    Args:
        *payloads: Payloads à inspecter dans l'ordre de priorité.

    Returns:
        Le premier identifiant non vide trouvé, sinon ``None``.
    """
    for payload in payloads:
        for key in ("id", "event_id", "uid"):
            value = payload.get(key)
            if value is None:
                continue

            normalized_value = str(value).strip()
            if normalized_value:
                return normalized_value
    return None
