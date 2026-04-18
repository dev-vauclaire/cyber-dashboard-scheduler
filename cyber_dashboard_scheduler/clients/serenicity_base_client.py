"""Socle HTTP partagé pour les clients Serenicity."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from cyber_dashboard_scheduler.utils import format_utc_datetime_for_api


class ApiClientError(RuntimeError):
    """Levée quand un appel API externe échoue ou retourne un format inattendu."""


class SerenicityBaseClient:
    """Mutualise la configuration HTTP et le décodage JSON Serenicity."""

    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: float) -> None:
        """Initialise la session HTTP Serenicity.

        Args:
            base_url: URL racine de l'API.
            api_key: Clé d'authentification Serenicity.
            timeout_seconds: Timeout réseau appliqué à chaque requête.

        Raises:
            ValueError: Si le timeout fourni n'est pas strictement positif.
        """
        if timeout_seconds <= 0:
            raise ValueError("Le timeout HTTP Serenicity doit être strictement positif")

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
        """Exécute une requête GET Serenicity et retourne le JSON décodé.

        Args:
            path: Chemin relatif de l'endpoint.
            params: Query params optionnels.

        Returns:
            Le corps JSON décodé.

        Raises:
            ApiClientError: Si l'appel HTTP échoue ou si la réponse JSON est invalide.
        """
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

    @staticmethod
    def _format_datetime(value: datetime) -> str:
        """Formate une date UTC au format attendu par Serenicity.

        Args:
            value: Date à formater.

        Returns:
            Une chaîne ISO 8601 suffixée par ``Z``.
        """
        return format_utc_datetime_for_api(value)

    @staticmethod
    def _extract_items(payload: Any, *, endpoint: str, resource_name: str) -> list[dict[str, Any]]:
        """Extrait une liste d'objets depuis les réponses standards Serenicity.

        Args:
            payload: Corps JSON brut.
            endpoint: Endpoint source pour enrichir les erreurs.
            resource_name: Libellé métier attendu dans les messages d'erreur.

        Returns:
            La liste d'objets décodée.

        Raises:
            ApiClientError: Si la structure de réponse ne contient pas une liste exploitable.
        """
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
            f"liste de {resource_name} introuvable"
        )

    @staticmethod
    def _parse_non_negative_int(value: Any, field_name: str, context_label: str) -> int:
        """Valide un entier positif ou nul renvoyé par Serenicity.

        Args:
            value: Valeur brute à convertir.
            field_name: Nom du champ concerné.
            context_label: Libellé métier du contexte courant.

        Returns:
            La valeur convertie en entier.

        Raises:
            ApiClientError: Si la valeur n'est pas un entier valide ou si elle est négative.
        """
        try:
            parsed_value = int(value)
        except (TypeError, ValueError) as exc:
            raise ApiClientError(
                f"Valeur entière invalide dans la réponse {context_label} : {field_name}"
            ) from exc

        if parsed_value < 0:
            raise ApiClientError(
                f"Valeur entière positive ou nulle attendue dans la réponse {context_label} : {field_name}"
            )
        return parsed_value
