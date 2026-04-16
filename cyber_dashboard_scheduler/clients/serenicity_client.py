"""Client HTTP minimal pour l'API Serenicity."""

from __future__ import annotations

from typing import Any

import requests


class ApiClientError(RuntimeError):
    """Levée quand un appel API externe échoue ou retourne un format inattendu."""


class SerenicityApiClient:
    """Expose les endpoints Serenicity nécessaires à l'inventaire."""

    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "Authorization": f"Api-Key {api_key}",
            }
        )

    def list_lurios(self) -> list[dict[str, Any]]:
        """Récupère les lurios depuis Serenicity."""
        payload = self._request_json("/lurios")
        return self._extract_items(payload, endpoint="/lurios")

    def list_sensors(self) -> list[dict[str, Any]]:
        """Récupère les capteurs Serenicity depuis l'API."""
        payload = self._request_json("/sensors")
        return self._extract_items(payload, endpoint="/sensors")

    def _request_json(self, path: str) -> Any:
        url = f"{self._base_url}{path}"
        try:
            response = self._session.get(url, timeout=self._timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ApiClientError(f"Échec de l'appel API Serenicity {url}: {exc}") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise ApiClientError(
                f"Réponse JSON invalide pour l'appel API Serenicity {url}"
            ) from exc

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
            "liste de sources introuvable"
        )
