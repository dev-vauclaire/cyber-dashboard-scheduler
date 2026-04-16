"""Repository d'accès à la table sensor_types."""

from __future__ import annotations

from psycopg import Connection

from cyber_dashboard_scheduler.models import SensorType


class SensorTypeRepository:
    """Expose les lectures nécessaires sur les types de capteurs."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def list_all(self) -> list[SensorType]:
        """Retourne tous les types de capteurs triés par identifiant."""
        query = """
            SELECT id, code, label, category
            FROM sensor_types
            ORDER BY id
        """
        with self._connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        return [
            SensorType(
                id=row["id"],
                code=row["code"],
                label=row["label"],
                category=row["category"],
            )
            for row in rows
        ]
