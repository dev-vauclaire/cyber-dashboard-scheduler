"""Connexion PostgreSQL et gestion simple des transactions."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from psycopg import Connection, OperationalError, connect
from psycopg.rows import dict_row

from cyber_dashboard_scheduler.config import DatabaseSettings


class PostgresDatabase:
    """Gère l'ouverture des connexions PostgreSQL du scheduler."""

    def __init__(self, settings: DatabaseSettings) -> None:
        self._settings = settings

    def open_connection(self) -> Connection:
        """Ouvre une connexion PostgreSQL avec des lignes sous forme de dictionnaires."""
        return connect(
            host=self._settings.host,
            port=self._settings.port,
            dbname=self._settings.name,
            user=self._settings.user,
            password=self._settings.password,
            row_factory=dict_row,
        )

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        """Ouvre puis ferme proprement une connexion PostgreSQL."""
        connection = self.open_connection()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        """Encadre une transaction avec commit ou rollback automatique."""
        with self.connection() as connection:
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()

    def check_connection(self) -> None:
        """Vérifie que PostgreSQL répond correctement."""
        try:
            with self.connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1 AS ok")
                    cursor.fetchone()
        except OperationalError as exc:
            raise RuntimeError(
                "Impossible de se connecter à PostgreSQL sur "
                f"{self._settings.host}:{self._settings.port}/{self._settings.name}"
            ) from exc