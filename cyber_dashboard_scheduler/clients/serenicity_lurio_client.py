"""Client Serenicity dédié aux lurios."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
import time
from typing import Any

from cyber_dashboard_scheduler.utils import normalize_datetime_to_utc

from .serenicity_base_client import (
    ApiClientError,
    ApiRateLimitError,
    SerenicityBaseClient,
)


LOGGER = logging.getLogger(__name__)
DEFAULT_LURIO_PAGE_DELAY_SECONDS = 0.5
DEFAULT_LURIO_MAX_PAGES_PER_CYCLE = 80


@dataclass(frozen=True, slots=True)
class SerenicityLurioReportFetchResult:
    """Résultat agrégé d'une lecture paginée de reports Lurio."""

    items: list[dict[str, Any]]
    pages_read: int
    total_count: int
    is_complete: bool
    last_report_created_at: datetime | None


class SerenicityLurioClient(SerenicityBaseClient):
    """Expose les endpoints Serenicity nécessaires aux lurios."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
        page_delay_seconds: float = DEFAULT_LURIO_PAGE_DELAY_SECONDS,
        max_pages_per_cycle: int = DEFAULT_LURIO_MAX_PAGES_PER_CYCLE,
    ) -> None:
        """Initialise le client Lurio et ses garde-fous de débit.

        Args:
            base_url: URL racine de l'API Serenicity.
            api_key: Clé d'authentification Serenicity.
            timeout_seconds: Timeout réseau appliqué à chaque requête.
            page_delay_seconds: Pause légère entre deux pages Lurio.
            max_pages_per_cycle: Nombre maximal de pages Lurio à lire par cycle.
        """
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
        if page_delay_seconds < 0:
            raise ValueError("Le délai entre pages Lurio ne peut pas être négatif")
        if max_pages_per_cycle <= 0:
            raise ValueError("Le nombre maximal de pages Lurio doit être strictement positif")
        self._page_delay_seconds = page_delay_seconds
        self._max_pages_per_cycle = max_pages_per_cycle

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
        is_complete = True
        last_report_created_at: datetime | None = None

        while True:
            payload = self._request_report_page(
                lurio_id=lurio_id,
                from_datetime=from_datetime,
                to_datetime=to_datetime,
                page_number=page_number,
            )
            parsed_page = self._parse_report_page_payload(payload)
            pages_read += 1
            items.extend(parsed_page["items"])
            total_count = parsed_page["total_count"]
            last_report_created_at = _extract_last_report_created_at(parsed_page["items"])

            if parsed_page["current_page"] >= parsed_page["last_page"]:
                break

            if pages_read >= self._max_pages_per_cycle:
                is_complete = False
                LOGGER.warning(
                    (
                        "Collecte Lurio tronquée pour %s: pages_lues=%s limite=%s "
                        "page_courante=%s derniere_page=%s"
                    ),
                    lurio_id,
                    pages_read,
                    self._max_pages_per_cycle,
                    parsed_page["current_page"],
                    parsed_page["last_page"],
                )
                break

            if self._page_delay_seconds > 0:
                time.sleep(self._page_delay_seconds)
            page_number = parsed_page["current_page"] + 1

        return SerenicityLurioReportFetchResult(
            items=items,
            pages_read=pages_read,
            total_count=total_count,
            is_complete=is_complete,
            last_report_created_at=last_report_created_at,
        )

    def _request_report_page(
        self,
        *,
        lurio_id: str,
        from_datetime: datetime,
        to_datetime: datetime,
        page_number: int,
    ) -> Any:
        """Récupère une page Lurio en respectant le rate limit indiqué par l'API."""
        while True:
            try:
                return self._request_json(
                    f"/lurios/{lurio_id}/reports",
                    params={
                        "from": self._format_datetime(from_datetime),
                        "to": self._format_datetime(to_datetime),
                        "page": page_number,
                    },
                )
            except ApiRateLimitError as exc:
                wait_seconds = exc.retry_after_seconds or 1.0
                LOGGER.warning(
                    (
                        "Rate limit Serenicity détecté pour le lurio %s page=%s. "
                        "Attente=%.2fs avant retry. reset=%s"
                    ),
                    lurio_id,
                    page_number,
                    wait_seconds,
                    exc.rate_limit_reset_at or "inconnu",
                )
                time.sleep(wait_seconds)

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


def _extract_last_report_created_at(items: list[dict[str, Any]]) -> datetime | None:
    """Retourne le `created_at` UTC du dernier item de la page si présent."""
    if not items:
        return None

    last_item = items[-1]
    created_at = last_item.get("created_at")
    if created_at is None:
        return None

    try:
        return normalize_datetime_to_utc(created_at, "created_at")
    except Exception:
        return None
