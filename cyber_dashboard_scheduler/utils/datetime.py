"""Utilitaires communs pour manipuler des dates en UTC."""

from __future__ import annotations

from datetime import UTC, datetime


def ensure_utc_datetime(value: datetime) -> datetime:
    """Retourne une date timezone-aware normalisée en UTC.

    Args:
        value: Date à normaliser.

    Returns:
        La date convertie en UTC.
    """
    normalized_value = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized_value.astimezone(UTC)


def format_utc_datetime_for_api(value: datetime) -> str:
    """Formate une date UTC au format ISO 8601 avec suffixe ``Z``.

    Args:
        value: Date à formater.

    Returns:
        La représentation ISO 8601 attendue par les APIs externes.
    """
    return ensure_utc_datetime(value).isoformat().replace("+00:00", "Z")


def to_database_timestamp(value: datetime | None) -> datetime | None:
    """Convertit une date UTC en ``TIMESTAMP`` PostgreSQL naïf.

    Args:
        value: Date applicative timezone-aware, ou ``None``.

    Returns:
        La date convertie sans information de fuseau pour rester cohérente avec
        le schéma PostgreSQL existant, ou ``None`` si aucune date n'est fournie.
    """
    if value is None:
        return None

    return ensure_utc_datetime(value).replace(tzinfo=None)


def from_database_timestamp(value: datetime | None) -> datetime | None:
    """Reconvertit un ``TIMESTAMP`` PostgreSQL en date UTC timezone-aware.

    Args:
        value: Date lue depuis PostgreSQL, ou ``None``.

    Returns:
        La date normalisée en UTC, ou ``None``.
    """
    if value is None:
        return None

    if value.tzinfo is not None:
        return value.astimezone(UTC)
    return value.replace(tzinfo=UTC)
