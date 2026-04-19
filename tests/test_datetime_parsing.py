"""Tests unitaires ciblés pour le parsing et la normalisation des dates."""

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

from cyber_dashboard_scheduler.models import SchedulerState
from cyber_dashboard_scheduler.services.collection_common import build_collection_window
from cyber_dashboard_scheduler.utils.normalization import (
    NormalizationError,
    normalize_datetime_to_utc,
)


class DatetimeParsingTestCase(unittest.TestCase):
    """Valide les cas critiques de parsing et de normalisation UTC."""

    def test_normalize_datetime_to_utc_supports_z_suffix(self) -> None:
        parsed_datetime = normalize_datetime_to_utc(
            "2026-04-18T10:00:00Z",
            "created_at",
        )

        self.assertEqual(parsed_datetime, datetime(2026, 4, 18, 10, 0, tzinfo=UTC))

    def test_normalize_datetime_to_utc_converts_offset_to_utc(self) -> None:
        parsed_datetime = normalize_datetime_to_utc(
            "2026-04-18T12:00:00+02:00",
            "created_at",
        )

        self.assertEqual(parsed_datetime, datetime(2026, 4, 18, 10, 0, tzinfo=UTC))

    def test_normalize_datetime_to_utc_rejects_invalid_string(self) -> None:
        with self.assertRaises(NormalizationError):
            normalize_datetime_to_utc("not-a-date", "created_at")

    def test_build_collection_window_uses_last_poll_at_and_safety_window(self) -> None:
        before = datetime(2026, 4, 18, 10, 0, tzinfo=UTC)
        current_state = SchedulerState(
            source_id=1,
            last_inventory_at=None,
            last_poll_at=datetime(2026, 4, 18, 9, 30, tzinfo=UTC),
            last_success_at=None,
            last_error_at=None,
            last_error_message=None,
        )

        collection_window = build_collection_window(
            before=before,
            current_state=current_state,
            safety_window_seconds=300,
        )

        self.assertEqual(
            collection_window.after,
            datetime(2026, 4, 18, 9, 25, tzinfo=UTC),
        )
        self.assertEqual(collection_window.before, before)


if __name__ == "__main__":
    unittest.main()
