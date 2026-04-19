"""Tests unitaires ciblés pour la sélection des sources par collecteur."""

from __future__ import annotations

from contextlib import contextmanager
import sys
from types import SimpleNamespace
from types import ModuleType
import unittest
from unittest.mock import patch

dotenv_stub = ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault("dotenv", dotenv_stub)

psycopg_stub = ModuleType("psycopg")
psycopg_stub.Connection = object
psycopg_stub.OperationalError = Exception
psycopg_stub.connect = lambda *args, **kwargs: None
sys.modules.setdefault("psycopg", psycopg_stub)

psycopg_rows_stub = ModuleType("psycopg.rows")
psycopg_rows_stub.dict_row = object()
sys.modules.setdefault("psycopg.rows", psycopg_rows_stub)

psycopg_types_stub = ModuleType("psycopg.types")
sys.modules.setdefault("psycopg.types", psycopg_types_stub)

psycopg_types_json_stub = ModuleType("psycopg.types.json")
psycopg_types_json_stub.Jsonb = lambda value: value
sys.modules.setdefault("psycopg.types.json", psycopg_types_json_stub)

from cyber_dashboard_scheduler.models import Source
from cyber_dashboard_scheduler.services.lurio_collection import (
    LurioAttackCollectionService,
)
from cyber_dashboard_scheduler.services.ogo_collection import OgoAttackCollectionService
from cyber_dashboard_scheduler.services.serenicity_sensor_collection import (
    SerenicitySensorAttackCollectionService,
)


class _FakeDatabase:
    """Base factice exposant uniquement ``connection`` pour les tests."""

    @contextmanager
    def connection(self):
        yield object()


class _FakeSourceRepository:
    """Repository factice renvoyant une liste de sources prédéfinie."""

    active_sources: list[Source] = []

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def list_active(self) -> list[Source]:
        return list(self.active_sources)


class CollectorSelectionTestCase(unittest.TestCase):
    """Vérifie la sélection des sources selon le type de collecteur."""

    def setUp(self) -> None:
        self.database = _FakeDatabase()
        self.sources = [
            Source("detoxio", "sensor-1", "Sensor 1", None, None, True),
            Source("lurio", "lurio-1", "Lurio 1", None, None, True),
            Source("waf", "ogo-site", "OGO Site", None, None, True),
        ]
        _FakeSourceRepository.active_sources = self.sources

    def test_sensor_collection_selects_only_detoxio_sources(self) -> None:
        service = SerenicitySensorAttackCollectionService(
            settings=SimpleNamespace(poll_safety_window_seconds=300),
            database=self.database,
            sensor_client=object(),
        )

        with patch(
            "cyber_dashboard_scheduler.services.serenicity_sensor_collection.SourceRepository",
            _FakeSourceRepository,
        ):
            selected_sources = service._load_active_sensor_sources()

        self.assertEqual([source.external_id for source in selected_sources], ["sensor-1"])

    def test_lurio_collection_selects_only_lurio_sources(self) -> None:
        service = LurioAttackCollectionService(
            settings=SimpleNamespace(poll_safety_window_seconds=300),
            database=self.database,
            lurio_client=object(),
        )

        with patch(
            "cyber_dashboard_scheduler.services.lurio_collection.SourceRepository",
            _FakeSourceRepository,
        ):
            selected_sources = service._load_active_lurio_sources()

        self.assertEqual([source.external_id for source in selected_sources], ["lurio-1"])

    def test_ogo_collection_selects_configured_waf_source(self) -> None:
        service = OgoAttackCollectionService(
            settings=SimpleNamespace(
                ogo=SimpleNamespace(site_name_or_id="ogo-site"),
                poll_safety_window_seconds=300,
            ),
            database=self.database,
            ogo_client=object(),
        )

        with patch(
            "cyber_dashboard_scheduler.services.ogo_collection.SourceRepository",
            _FakeSourceRepository,
        ):
            selected_source = service._load_active_ogo_source()

        self.assertEqual(selected_source.sensor_type_code, "waf")
        self.assertEqual(selected_source.external_id, "ogo-site")


if __name__ == "__main__":
    unittest.main()
