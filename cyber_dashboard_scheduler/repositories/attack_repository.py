"""Repository d'accès à la table attacks."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from psycopg import Connection
from psycopg.types.json import Jsonb

from cyber_dashboard_scheduler.models import Attack


class AttackRepository:
    """Expose l'insertion idempotente des attaques."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def insert(self, attack: Attack) -> bool:
        """Insère une attaque si son deduplication_id n'existe pas déjà."""
        source_id = self._resolve_source_id(
            sensor_type_code=attack.sensor_type_code,
            external_id=attack.source_external_id,
        )
        deduplication_id = _build_deduplication_id(
            source_id=source_id,
            attacker_ip=attack.attacker_ip,
            occured_at=attack.occured_at,
        )
        query = """
            INSERT INTO attacks (
                deduplication_id,
                source_id,
                source_event_id,
                attacker_ip,
                occured_at,
                collected_at,
                attack_type,
                raw_payload,
                correlation_status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending')
            ON CONFLICT (deduplication_id) DO NOTHING
            RETURNING id
        """
        params = (
            deduplication_id,
            source_id,
            attack.source_event_id,
            attack.attacker_ip,
            _to_database_timestamp(attack.occured_at),
            _to_database_timestamp(attack.collected_at),
            attack.attack_type,
            Jsonb(attack.raw_payload) if attack.raw_payload is not None else None,
        )
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()

        return row is not None

    def _resolve_source_id(self, *, sensor_type_code: str, external_id: str) -> int:
        query = """
            SELECT s.id
            FROM sources AS s
            INNER JOIN sensor_types AS st ON st.id = s.sensor_type_id
            WHERE st.code = %s
              AND s.external_id = %s
        """
        with self._connection.cursor() as cursor:
            cursor.execute(query, (sensor_type_code, external_id))
            row = cursor.fetchone()

        if row is None:
            raise ValueError(
                "Source introuvable en base pour l'insertion d'attaque : "
                f"{sensor_type_code}/{external_id}"
            )

        return row["id"]


def _build_deduplication_id(
    *,
    source_id: int,
    attacker_ip: str,
    occured_at: datetime,
) -> str:
    normalized_occured_at = (
        occured_at if occured_at.tzinfo is not None else occured_at.replace(tzinfo=UTC)
    )
    occured_at_utc = normalized_occured_at.astimezone(UTC).isoformat()
    digest = sha256(f"{source_id}|{attacker_ip}|{occured_at_utc}".encode("utf-8"))
    return digest.hexdigest()


def _to_database_timestamp(value: datetime) -> datetime:
    normalized_value = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    normalized_value = normalized_value.astimezone(UTC)
    return normalized_value.replace(tzinfo=None)
