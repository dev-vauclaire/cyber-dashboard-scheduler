"""Client Serenicity dédié aux lurios."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .serenicity_base_client import ApiClientError, SerenicityBaseClient


@dataclass(frozen=True, slots=True)
class SerenicityLurioReportFetchResult:
    """Résultat agrégé d'une lecture paginée de reports Lurio."""

    items: list[dict[str, Any]]
    pages_read: int
    total_count: int


class SerenicityLurioClient(SerenicityBaseClient):
    """Expose les endpoints Serenicity nécessaires aux lurios."""

    def list_lurios(self) -> list[dict[str, Any]]:
        """Récupère les lurios depuis Serenicity.

        Returns:
            La liste brute des lurios.

        Raises:
            ApiClientError: Si l'appel réseau ou le format de réponse échoue.
        """
        payload = self._request_json("/lurios")
        return self._extract_items(payload, endpoint="/lurios", resource_name="lurios")

    def list_lurio_reports(
        self,
        *,
        lurio_id: str,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> SerenicityLurioReportFetchResult:
        """Lit toutes les pages de reports d'un lurio Serenicity.

        Args:
            lurio_id: Identifiant du lurio ciblé.
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
                f"/lurios/{lurio_id}/reports",
                params={
                    "from": self._format_datetime(from_datetime),
                    "to": self._format_datetime(to_datetime),
                    "page": page_number,
                },
            )
            parsed_page = self._parse_report_page_payload(payload)
            pages_read += 1
            items.extend(parsed_page["items"])
            total_count = parsed_page["total_count"]

            if parsed_page["current_page"] >= parsed_page["last_page"]:
                break
            page_number = parsed_page["current_page"] + 1

        return SerenicityLurioReportFetchResult(
            items=items,
            pages_read=pages_read,
            total_count=total_count,
        )

    @staticmethod
    def _parse_report_page_payload(payload: Any) -> dict[str, Any]:
        """Valide la structure paginée d'une réponse de reports Lurio.

        Args:
            payload: Corps JSON brut.

        Returns:
            Un dictionnaire homogène contenant les items et la pagination.

        Raises:
            ApiClientError: Si la réponse n'a pas le format attendu.
        """
        if not isinstance(payload, dict):
            raise ApiClientError("Format inattendu pour la réponse de report Lurio")

        meta = payload.get("meta")
        items = payload.get("data")

        if not isinstance(meta, dict):
            raise ApiClientError("Format inattendu pour meta dans la réponse Lurio")
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ApiClientError("Format inattendu pour data dans la réponse Lurio")

        current_page = SerenicityBaseClient._parse_non_negative_int(
            meta.get("current_page", 1),
            "current_page",
            "Lurio",
        )
        last_page = SerenicityBaseClient._parse_non_negative_int(
            meta.get("last_page", 1),
            "last_page",
            "Lurio",
        )
        total_count = SerenicityBaseClient._parse_non_negative_int(
            meta.get("total", 0),
            "total",
            "Lurio",
        )

        if not items and current_page in {0, 1} and last_page in {0, 1}:
            return {
                "items": [],
                "current_page": max(current_page, 1),
                "last_page": max(last_page, 1),
                "total_count": total_count,
            }

        if current_page <= 0 or last_page <= 0:
            raise ApiClientError("La pagination Lurio est invalide pour une réponse non vide")

        return {
            "items": items,
            "current_page": current_page,
            "last_page": last_page,
            "total_count": total_count,
        }
