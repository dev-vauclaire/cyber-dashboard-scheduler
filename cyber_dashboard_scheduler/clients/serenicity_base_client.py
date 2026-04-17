"""Socle HTTP partagé pour les clients Serenicity."""

from __future__ import annotations

from typing import Any

import requests


class ApiClientError(RuntimeError):
    """Levée quand un appel API externe échoue ou retourne un format inattendu."""


class SerenicityBaseClient:
    """Mutualise la configuration HTTP et le décodage JSON Serenicity."""

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

    def _request_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        """Exécute une requête GET Serenicity et retourne le JSON décodé."""
        url = f"{self._base_url}{path}"
        try:
            response = self._session.get(url, params=params, timeout=self._timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ApiClientError(f"Échec de l'appel API Serenicity {url}: {exc}") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise ApiClientError(
                f"Réponse JSON invalide pour l'appel API Serenicity {url}"
            ) from exc
