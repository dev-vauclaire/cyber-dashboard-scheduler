"""Client Serenicity dédié aux capteurs et à leurs flux."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
        """Récupère les capteurs Serenicity depuis l'API.

        Returns:
            La liste brute des capteurs.

        Raises:
            ApiClientError: Si l'appel réseau ou le format de réponse échoue.
        """
        payload = self._request_json("/sensors")
        return self._extract_items(payload, endpoint="/sensors", resource_name="capteurs")

    def list_sensor_fluxes(
        self,
        *,
        sensor_id: str,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> SerenicitySensorFluxFetchResult:
        """Lit toutes les pages de flux d'un capteur Serenicity.

        Args:
            sensor_id: Identifiant du capteur ciblé.
            from_datetime: Borne basse UTC incluse.
            to_datetime: Borne haute UTC.

        Returns:
            Le résultat agrégé contenant toutes les pages lues.

        Raises:
            ApiClientError: Si une page de réponse est invalide.
        """
        page_number = 1
        pages_read = 0
        items: list[dict[str, Any]] = []
        total_count = 0

        while True:
            payload = self._request_json(
                f"/sensors/{sensor_id}/flux",
                params={
                    "from": self._format_datetime(from_datetime),
                    "to": self._format_datetime(to_datetime),
                    "only_toxic": "true",
                    "page": page_number,
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
    def _parse_flux_page_payload(payload: Any) -> dict[str, Any]:
        """Valide la structure paginée d'une réponse de flux Serenicity.

        Args:
            payload: Corps JSON brut.

        Returns:
            Un dictionnaire homogène contenant les items et la pagination.

        Raises:
            ApiClientError: Si la réponse n'a pas le format attendu.
        """
        if not isinstance(payload, dict):
            raise ApiClientError("Format inattendu pour la réponse de flux Serenicity")

        meta = payload.get("meta")
        items = payload.get("data")

        if not isinstance(meta, dict):
            raise ApiClientError("Format inattendu pour meta dans la réponse Serenicity")
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ApiClientError("Format inattendu pour data dans la réponse Serenicity")

        current_page = SerenicityBaseClient._parse_non_negative_int(
            meta.get("current_page", 1),
            "current_page",
            "Serenicity",
        )
        last_page = SerenicityBaseClient._parse_non_negative_int(
            meta.get("last_page", 1),
            "last_page",
            "Serenicity",
        )
        total_count = SerenicityBaseClient._parse_non_negative_int(
            meta.get("total", 0),
            "total",
            "Serenicity",
        )

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
