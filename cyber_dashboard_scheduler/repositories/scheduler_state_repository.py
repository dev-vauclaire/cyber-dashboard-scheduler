"""Repository d'accès à la table scheduler_state."""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection

from cyber_dashboard_scheduler.models import SchedulerState, Source
from cyber_dashboard_scheduler.utils import from_database_timestamp, to_database_timestamp


class SchedulerStateRepository:
    """Expose les lectures et écritures nécessaires sur l'état du scheduler."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get_by_source(self, source: Source) -> SchedulerState | None:
        """Retourne l'état du scheduler pour une source donnée."""
        source_id = self._resolve_source_id(
            sensor_type_code=source.sensor_type_code,
            external_id=source.external_id,
            raise_if_missing=False,
        )
        if source_id is None:
            return None

        query = """
            SELECT
                source_id,
                last_inventory_at,
                last_poll_at,
                last_success_at,
                last_error_at,
                last_error_message
            FROM scheduler_state
            WHERE source_id = %s
        """
        with self._connection.cursor() as cursor:
            cursor.execute(query, (source_id,))
            row = cursor.fetchone()

        if row is None:
            return None

        return self._map_row(row)

    def upsert(
        self,
        source: Source,
        *,
        last_inventory_at: datetime | None = None,
        last_poll_at: datetime | None = None,
        last_success_at: datetime | None = None,
        last_error_at: datetime | None = None,
        last_error_message: str | None = None,
    ) -> SchedulerState:
        """Insère ou met à jour l'état du scheduler d'une source."""
        source_id = self._resolve_source_id(
            sensor_type_code=source.sensor_type_code,
            external_id=source.external_id,
            raise_if_missing=True,
        )
        query = """
            INSERT INTO scheduler_state (
                source_id,
                last_inventory_at,
                last_poll_at,
                last_success_at,
                last_error_at,
                last_error_message
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id)
            DO UPDATE SET
                last_inventory_at = EXCLUDED.last_inventory_at,
                last_poll_at = EXCLUDED.last_poll_at,
                last_success_at = EXCLUDED.last_success_at,
                last_error_at = EXCLUDED.last_error_at,
                last_error_message = EXCLUDED.last_error_message
            RETURNING
                source_id,
                last_inventory_at,
                last_poll_at,
                last_success_at,
                last_error_at,
                last_error_message
        """
        params = (
            source_id,
            to_database_timestamp(last_inventory_at),
            to_database_timestamp(last_poll_at),
            to_database_timestamp(last_success_at),
            to_database_timestamp(last_error_at),
            last_error_message,
        )
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError("L'upsert de scheduler_state n'a retourné aucune ligne")

        return self._map_row(row)

    def _resolve_source_id(
        self,
        *,
        sensor_type_code: str,
        external_id: str,
        raise_if_missing: bool,
    ) -> int | None:
        """Résout l'identifiant d'une source pour les opérations d'état.

        Args:
            sensor_type_code: Code métier du type de capteur.
            external_id: Identifiant externe de la source.
            raise_if_missing: Indique s'il faut lever une erreur si la source est absente.

        Returns:
            L'identifiant ``sources.id`` ou ``None`` si autorisé.

        Raises:
            ValueError: Si la source est absente et que ``raise_if_missing`` vaut ``True``.
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
            if raise_if_missing:
                raise ValueError(
                    "Source introuvable en base pour scheduler_state : "
                    f"{sensor_type_code}/{external_id}"
                )
            return None

        return row["id"]

    @staticmethod
    def _map_row(row: dict) -> SchedulerState:
        """Convertit une ligne SQL en modèle applicatif UTC.

        Args:
            row: Ligne brute renvoyée par psycopg.

        Returns:
            L'état applicatif associé.
        """
        return SchedulerState(
            source_id=row["source_id"],
            last_inventory_at=from_database_timestamp(row["last_inventory_at"]),
            last_poll_at=from_database_timestamp(row["last_poll_at"]),
            last_success_at=from_database_timestamp(row["last_success_at"]),
            last_error_at=from_database_timestamp(row["last_error_at"]),
            last_error_message=row["last_error_message"],
        )
