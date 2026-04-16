"""Repository d'accès à la table sources."""

from __future__ import annotations

from psycopg import Connection

from cyber_dashboard_scheduler.models import Source


class SourceRepository:
    """Expose les lectures et écritures nécessaires sur les sources."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def list_active(self) -> list[Source]:
        """Retourne les sources actives avec leur code de type de capteur."""
        query = """
            SELECT
                st.code AS sensor_type_code,
                s.external_id,
                s.name,
                s.latitude,
                s.longitude,
                s.is_active
            FROM sources AS s
            INNER JOIN sensor_types AS st ON st.id = s.sensor_type_id
            WHERE s.is_active = TRUE
            ORDER BY st.code, s.external_id
        """
        with self._connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        return [self._map_row(row) for row in rows]

    def upsert(self, source: Source) -> Source:
        """Insère ou met à jour une source à partir de son type et de son external_id."""
        sensor_type_id = self._resolve_sensor_type_id(source.sensor_type_code)
        query = """
            INSERT INTO sources (
                sensor_type_id,
                external_id,
                name,
                latitude,
                longitude,
                is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (sensor_type_id, external_id)
            DO UPDATE SET
                name = EXCLUDED.name,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                is_active = EXCLUDED.is_active
            RETURNING external_id, name, latitude, longitude, is_active
        """
        params = (
            sensor_type_id,
            source.external_id,
            source.name,
            source.latitude,
            source.longitude,
            source.is_active,
        )
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError("L'upsert de la source n'a retourné aucune ligne")

        return Source(
            sensor_type_code=source.sensor_type_code,
            external_id=row["external_id"],
            name=row["name"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            is_active=row["is_active"],
        )

    def _resolve_sensor_type_id(self, sensor_type_code: str) -> int:
        query = """
            SELECT id
            FROM sensor_types
            WHERE code = %s
        """
        with self._connection.cursor() as cursor:
            cursor.execute(query, (sensor_type_code,))
            row = cursor.fetchone()

        if row is None:
            raise ValueError(
                f"Type de capteur introuvable dans sensor_types : {sensor_type_code}"
            )

        return row["id"]

    @staticmethod
    def _map_row(row: dict) -> Source:
        external_id = row["external_id"]
        if external_id is None:
            raise RuntimeError("La source lue en base ne contient pas d'external_id")

        return Source(
            sensor_type_code=row["sensor_type_code"],
            external_id=external_id,
            name=row["name"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            is_active=row["is_active"],
        )
