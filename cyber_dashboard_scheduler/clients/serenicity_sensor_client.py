"""Client Serenicity dédié aux capteurs et à leurs flux."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .serenicity_base_client import ApiClientError, SerenicityBaseClient


@dataclass(frozen=True, slots=True)
class SerenicitySensorFluxFetchResult:
    """Résultat agrégé d'une lecture paginée de flux Serenicity."""

    items: list[dict[str, Any]]
    pages_read: int
    total_count: int


class SerenicitySensorClient(SerenicityBaseClient):
    """Expose les endpoints Serenicity nécessaires aux capteurs."""

    def list_sensors(self) -> list[dict[str, Any]]:
        """Récupère les capteurs Serenicity depuis l'API."""
        payload = self._request_json("/sensors")
        return self._extract_items(payload, endpoint="/sensors")

    def list_sensor_fluxes(
        self,
        *,
        sensor_id: str,
        from_datetime: datetime,
        to_datetime: datetime,
        sort_desc: bool = True,
    ) -> SerenicitySensorFluxFetchResult:
        """Lit toutes les pages de flux d'un capteur Serenicity."""
        page_number = 1
        pages_read = 0
        items: list[dict[str, Any]] = []
        total_count = 0

        while True:
            payload = self._request_json(
                f"/sensors/{sensor_id}/flux",
                params={
                    "from": _format_serenicity_datetime(from_datetime),
                    "to": _format_serenicity_datetime(to_datetime),
                    "only_toxic": "true",
                    "page": page_number,
                    #"sort_by": "startOfHour",
                    #"sort_desc": str(sort_desc).lower(),
                },
            )
            parsed_page = self._parse_flux_page_payload(payload)
            pages_read += 1
            items.extend(parsed_page["items"])
            total_count = parsed_page["total_count"]

            if parsed_page["current_page"] >= parsed_page["last_page"]:
                break
            page_number = parsed_page["current_page"] + 1

        return SerenicitySensorFluxFetchResult(
            items=items,
            pages_read=pages_read,
            total_count=total_count,
        )

    @staticmethod
    def _extract_items(payload: Any, *, endpoint: str) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            if all(isinstance(item, dict) for item in payload):
                return payload
            raise ApiClientError(
                f"Format inattendu pour l'endpoint Serenicity {endpoint}: liste invalide"
            )

        if isinstance(payload, dict):
            for key in ("data", "items", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    if all(isinstance(item, dict) for item in value):
                        return value
                    raise ApiClientError(
                        f"Format inattendu pour l'endpoint Serenicity {endpoint}: "
                        f"contenu invalide dans {key}"
                    )

        raise ApiClientError(
            f"Format inattendu pour l'endpoint Serenicity {endpoint}: "
            "liste de capteurs introuvable"
        )

    @staticmethod
    def _parse_flux_page_payload(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ApiClientError("Format inattendu pour la réponse de flux Serenicity")

        meta = payload.get("meta")
        items = payload.get("data")

        if not isinstance(meta, dict):
            raise ApiClientError("Format inattendu pour meta dans la réponse Serenicity")
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ApiClientError("Format inattendu pour data dans la réponse Serenicity")

        current_page = _parse_non_negative_int(meta.get("current_page", 1), "current_page")
        last_page = _parse_non_negative_int(meta.get("last_page", 1), "last_page")
        total_count = _parse_non_negative_int(meta.get("total", 0), "total")

        if not items and current_page in {0, 1} and last_page in {0, 1}:
            return {
                "items": [],
                "current_page": max(current_page, 1),
                "last_page": max(last_page, 1),
                "total_count": total_count,
            }

        if current_page <= 0 or last_page <= 0:
            raise ApiClientError("La pagination Serenicity est invalide pour une réponse non vide")

        return {
            "items": items,
            "current_page": current_page,
            "last_page": last_page,
            "total_count": total_count,
        }


def _format_serenicity_datetime(value: datetime) -> str:
    """Formate une date en UTC pour les appels Serenicity."""
    normalized_value = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized_value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_non_negative_int(value: Any, field_name: str) -> int:
    try:
        parsed_value = int(value)
    except (TypeError, ValueError) as exc:
        raise ApiClientError(
            f"Valeur entière invalide dans la réponse Serenicity : {field_name}"
        ) from exc

    if parsed_value < 0:
        raise ApiClientError(
            f"Valeur entière positive ou nulle attendue dans la réponse Serenicity : {field_name}"
        )
    return parsed_value
