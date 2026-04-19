"""Repository d'accès à la table attacks."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256

from psycopg import Connection
from psycopg.types.json import Jsonb

from cyber_dashboard_scheduler.models import Attack
from cyber_dashboard_scheduler.utils import ensure_utc_datetime, to_database_timestamp


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
            occurred_at=attack.occurred_at,
        )
        query = """
            INSERT INTO attacks (
                deduplication_id,
                source_id,
                source_event_id,
                attacker_ip,
                occurred_at,
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
            to_database_timestamp(attack.occurred_at),
            to_database_timestamp(attack.collected_at),
            attack.attack_type,
            Jsonb(attack.raw_payload) if attack.raw_payload is not None else None,
        )
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()

        return row is not None

    def _resolve_source_id(self, *, sensor_type_code: str, external_id: str) -> int:
        """Retourne l'identifiant technique d'une source déjà persistée.

        Args:
            sensor_type_code: Code fonctionnel du type de capteur.
            external_id: Identifiant externe de la source.

        Returns:
            L'identifiant ``sources.id`` correspondant.

        Raises:
            ValueError: Si la source n'existe pas en base.
        """
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
    occurred_at: datetime,
) -> str:
    """Construit la clé idempotente alignée avec les règles d'unicité métier.

    Args:
        source_id: Identifiant interne de la source.
        attacker_ip: Adresse IP attaquante normalisée.
        occurred_at: Date métier de l'attaque.

    Returns:
        Un hash SHA-256 stable.
    """
    occurred_at_utc = ensure_utc_datetime(occurred_at).isoformat()
    digest = sha256(f"{source_id}|{attacker_ip}|{occurred_at_utc}".encode("utf-8"))
    return digest.hexdigest()
