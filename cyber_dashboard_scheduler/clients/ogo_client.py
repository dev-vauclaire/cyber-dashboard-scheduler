"""Client HTTP minimal pour l'API OGO."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
import hashlib
from urllib.parse import urlencode

import requests

from .serenicity_client import ApiClientError


@dataclass(frozen=True, slots=True)
class OgoJournalFetchResult:
    """Résultat agrégé de la lecture paginée du journal OGO."""

    items: list[dict[str, Any]]
    pages_read: int
    total_count: int

class OgoApiClient:
    """Expose les endpoints OGO nécessaires à la collecte d'attaques."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        api_key: str,
        site_name_or_id: str,
        timeout_seconds: float,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username.strip()
        self._api_key = api_key
        self._site_name_or_id = site_name_or_id.strip()
        self._timeout_seconds = timeout_seconds
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    def list_security_events(
        self,
        *,
        after: datetime,
        before: datetime,
    ) -> OgoJournalFetchResult:
        """Lit toutes les pages du journal OGO pour les événements SECURITY."""
        page_size = 20
        page_number = 1
        pages_read = 0
        items: list[dict[str, Any]] = []
        total_count = 0
        endpoint = f"/api/{self._username}/journal"
        while True:
            payload = self._request_json(
                path=endpoint,
                params={
                    "t": _generate_ogo_auth_token(endpoint, self._api_key),
                    "type": "SECURITY",
                    "sites": self._site_name_or_id,
                    "after": _format_ogo_datetime(after),
                    "before": _format_ogo_datetime(before),
                    "page": page_number,
                    "size": page_size,
                },
            )
            parsed_page = self._parse_page_payload(payload)
            pages_read += 1
            items.extend(parsed_page["items"])
            total_count = parsed_page["total_count"]

            if parsed_page["page_number"] >= parsed_page["total_pages"]:
                break
            page_number = parsed_page["page_number"] + 1

        return OgoJournalFetchResult(
            items=items,
            pages_read=pages_read,
            total_count=total_count,
        )

    def _request_json(self, *, path: str, params: dict[str, Any]) -> Any:
        url = f"{self._base_url}{path}"
        try:
            response = self._session.get(
                url,
                params=params,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ApiClientError(f"Échec de l'appel API OGO {url}: {exc}") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise ApiClientError(
                f"Réponse JSON invalide pour l'appel API OGO {url}"
            ) from exc

    @staticmethod
    def _parse_page_payload(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ApiClientError("Format inattendu pour la réponse du journal OGO")

        if payload.get("hasError") is True:
            raise ApiClientError("L'API OGO a indiqué une erreur sur la réponse journal")

        total_pages = _parse_non_negative_int(payload.get("totalPages"), "totalPages")
        total_count = _parse_non_negative_int(payload.get("totalCount"), "totalCount")
        page_number = _parse_non_negative_int(payload.get("pageNumber", 0), "pageNumber")
        items = payload.get("items")

        if _is_empty_journal_payload(
            payload=payload,
            items=items,
            total_pages=total_pages,
            total_count=total_count,
            page_number=page_number,
        ):
            return {
                "items": [],
                "total_pages": 0,
                "page_number": 0,
                "total_count": 0,
            }

        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ApiClientError("Format inattendu pour le champ items du journal OGO")

        if total_pages == 0 and page_number == 0:
            return {
                "items": items,
                "total_pages": total_pages,
                "page_number": page_number,
                "total_count": total_count,
            }
        if total_pages <= 0 or page_number <= 0:
            raise ApiClientError(
                "La pagination du journal OGO est invalide pour une réponse non vide"
            )

        return {
            "items": items,
            "total_pages": total_pages,
            "page_number": page_number,
            "total_count": total_count,
        }


def _generate_ogo_auth_token(endpoint: str, api_key: str) -> str:
    raw = f"{endpoint}-{api_key}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _format_ogo_datetime(value: datetime) -> str:
    normalized_value = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized_value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_non_negative_int(value: Any, field_name: str) -> int:
    try:
        parsed_value = int(value)
    except (TypeError, ValueError) as exc:
        raise ApiClientError(
            f"Valeur entière invalide dans la réponse OGO : {field_name}"
        ) from exc

    if parsed_value < 0:
        raise ApiClientError(
            f"Valeur entière positive ou nulle attendue dans la réponse OGO : {field_name}"
        )
    return parsed_value


def _is_empty_journal_payload(
    *,
    payload: dict[str, Any],
    items: Any,
    total_pages: int,
    total_count: int,
    page_number: int,
) -> bool:
    status = payload.get("status")
    status_code = None
    if isinstance(status, dict) and status.get("code") is not None:
        status_code = str(status.get("code")).strip()

    if isinstance(items, list) and len(items) == 0 and total_count == 0 and total_pages == 0:
        return True

    if items is None and total_count == 0 and total_pages == 0 and page_number == 0:
        return status_code == "903"

    return False
