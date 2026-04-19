"""Tests unitaires ciblés pour la normalisation métier du scheduler."""

from __future__ import annotations

from datetime import UTC, datetime
import sys
from types import ModuleType
import unittest

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
from cyber_dashboard_scheduler.services.attack_normalization import (
    normalize_ogo_attack,
    normalize_serenicity_sensor_flux,
)
from cyber_dashboard_scheduler.services.source_normalization import (
    normalize_lurio_source,
)


class AttackNormalizationTestCase(unittest.TestCase):
    """Valide quelques scénarios critiques de normalisation."""

    def test_normalize_ogo_attack_returns_none_when_site_does_not_match(self) -> None:
        source = Source(
            sensor_type_code="waf",
            external_id="site-a",
            name="Site A",
            latitude=None,
            longitude=None,
            is_active=True,
        )

        attack = normalize_ogo_attack(
            source,
            {
                "site": "site-b",
                "date": "2026-04-18T10:00:00Z",
                "event": {"ip": "203.0.113.10", "type": "sql-injection"},
            },
            collected_at="2026-04-18T10:05:00Z",
        )

        self.assertIsNone(attack)

    def test_normalize_serenicity_sensor_flux_normalizes_attack(self) -> None:
        source = Source(
            sensor_type_code="detoxio",
            external_id="sensor-1",
            name="Sensor 1",
            latitude=None,
            longitude=None,
            is_active=True,
        )

        attack = normalize_serenicity_sensor_flux(
            source,
            {
                "id": "flux-1",
                "toxic": True,
                "ip1": "203.0.113.10",
                "start_of_hour": "2026-04-18T12:00:00+02:00",
                "protocol": "http",
            },
            collected_at="2026-04-18T10:05:00Z",
        )

        self.assertIsNotNone(attack)
        assert attack is not None
        self.assertEqual(attack.source_event_id, "flux-1")
        self.assertEqual(attack.attacker_ip, "203.0.113.10")
        self.assertEqual(attack.attack_type, "http")
        self.assertEqual(attack.occurred_at, datetime(2026, 4, 18, 10, 0, tzinfo=UTC))
        self.assertEqual(attack.collected_at, datetime(2026, 4, 18, 10, 5, tzinfo=UTC))


class SourceNormalizationTestCase(unittest.TestCase):
    """Valide les règles minimales de normalisation des sources."""

    def test_normalize_lurio_source_marks_connected_source_as_active(self) -> None:
        source = normalize_lurio_source(
            {
                "id": "lurio-1",
                "name": "Lurio Paris",
                "status": "CONNECTED",
                "latitude": "48.8566",
                "longitude": "2.3522",
            }
        )

        self.assertEqual(source.sensor_type_code, "lurio")
        self.assertEqual(source.external_id, "lurio-1")
        self.assertTrue(source.is_active)


if __name__ == "__main__":
    unittest.main()
