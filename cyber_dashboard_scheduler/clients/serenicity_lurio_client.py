"""Client Serenicity dédié aux lurios."""

from __future__ import annotations

from typing import Any

from .serenicity_base_client import ApiClientError, SerenicityBaseClient


class SerenicityLurioClient(SerenicityBaseClient):
    """Expose les endpoints Serenicity nécessaires aux lurios."""

    def list_lurios(self) -> list[dict[str, Any]]:
        """Récupère les lurios depuis Serenicity."""
        payload = self._request_json("/lurios")
        return self._extract_items(payload, endpoint="/lurios")

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
            "liste de lurios introuvable"
        )
