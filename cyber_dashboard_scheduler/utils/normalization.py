"""Utilitaires partagés pour la normalisation des données externes."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Any, Mapping

from .color import require_hex_color


class NormalizationError(ValueError):
    """Levée quand un payload externe ne peut pas être normalisé."""


def require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    """Valide qu'un champ obligatoire est un mapping."""
    if not isinstance(value, Mapping):
        raise NormalizationError(f"Champ obligatoire invalide : {field_name}")
    return value


def require_text(value: Any, field_name: str) -> str:
    """Valide qu'un champ obligatoire est une chaîne non vide."""
    if not isinstance(value, str) or not value.strip():
        raise NormalizationError(f"Champ obligatoire invalide : {field_name}")
    return value.strip()


def require_identifier(value: Any, field_name: str) -> str:
    """Valide qu'un identifiant obligatoire est présent."""
    if value is None:
        raise NormalizationError(f"Champ obligatoire invalide : {field_name}")

    text_value = str(value).strip()
    if not text_value:
        raise NormalizationError(f"Champ obligatoire invalide : {field_name}")
    return text_value


def optional_text(value: Any) -> str | None:
    """Retourne un texte nettoyé ou `None`."""
    if value is None:
        return None
    if not isinstance(value, str):
        return None

    normalized_value = value.strip()
    return normalized_value or None


def optional_float(
    value: Any,
    field_name: str,
    min_value: float,
    max_value: float,
) -> float | None:
    """Convertit un flottant optionnel en contrôlant sa plage de validité."""
    if value is None or value == "":
        return None

    try:
        normalized_value = float(value)
    except (TypeError, ValueError) as exc:
        raise NormalizationError(
            f"Champ numérique invalide : {field_name}"
        ) from exc

    if normalized_value < min_value or normalized_value > max_value:
        raise NormalizationError(
            f"Champ numérique hors limites : {field_name}"
        )

    return normalized_value


def require_ip(value: Any, field_name: str) -> str:
    """Valide une adresse IP et retourne sa représentation normalisée."""
    ip_value = require_text(value, field_name)

    try:
        return str(ip_address(ip_value))
    except ValueError as exc:
        raise NormalizationError(f"Adresse IP invalide : {field_name}") from exc


def normalize_datetime_to_utc(value: datetime | str | None, field_name: str) -> datetime:
    """Convertit une date en `datetime` timezone-aware en UTC."""
    if value is None:
        raise NormalizationError(f"Champ obligatoire invalide : {field_name}")

    if isinstance(value, datetime):
        parsed_value = value
    elif isinstance(value, str):
        text_value = value.strip()
        if not text_value:
            raise NormalizationError(f"Champ obligatoire invalide : {field_name}")

        if text_value.endswith("Z"):
            text_value = f"{text_value[:-1]}+00:00"

        try:
            parsed_value = datetime.fromisoformat(text_value)
        except ValueError as exc:
            raise NormalizationError(
                f"Date invalide pour le champ : {field_name}"
            ) from exc
    else:
        raise NormalizationError(f"Champ obligatoire invalide : {field_name}")

    if parsed_value.tzinfo is None:
        parsed_value = parsed_value.replace(tzinfo=UTC)

    return parsed_value.astimezone(UTC)


def normalize_collected_at(value: datetime | str | None) -> datetime:
    """Normalise la date de collecte ou utilise l'instant courant UTC."""
    if value is None:
        return datetime.now(UTC)
    return normalize_datetime_to_utc(value, "collected_at")


def copy_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Retourne une copie du payload brut à conserver."""
    return deepcopy(dict(payload))


def to_bool(value: Any) -> bool:
    """Convertit des représentations simples en booléen."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    if isinstance(value, int):
        return value != 0
    return False
