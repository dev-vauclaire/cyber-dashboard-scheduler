"""Socle HTTP partagé pour les clients Serenicity."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from cyber_dashboard_scheduler.utils import format_utc_datetime_for_api


LOGGER = logging.getLogger(__name__)
SERENICITY_HTTP_RETRY_COUNT = 2
SERENICITY_HTTP_RETRY_BACKOFF_SECONDS = 0.5


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
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._session = self._build_session()

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
            self._reset_session_after_failure()
            raise ApiClientError(f"Échec de l'appel API Serenicity {url}: {exc}") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise ApiClientError(
                f"Réponse JSON invalide pour l'appel API Serenicity {url}"
            ) from exc

    def _build_session(self) -> requests.Session:
        """Construit une session HTTP Serenicity avec retry sur les GET idempotents."""
        session = requests.Session()
        session.headers.update(
            {
                "Accept": "application/json",
                "Authorization": f"Api-Key {self._api_key}",
                "Connection": "close",
            }
        )
        retry_policy = Retry(
            total=SERENICITY_HTTP_RETRY_COUNT,
            connect=SERENICITY_HTTP_RETRY_COUNT,
            read=SERENICITY_HTTP_RETRY_COUNT,
            status=SERENICITY_HTTP_RETRY_COUNT,
            backoff_factor=SERENICITY_HTTP_RETRY_BACKOFF_SECONDS,
            allowed_methods=frozenset({"GET"}),
            status_forcelist=(429, 500, 502, 503, 504),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_policy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _reset_session_after_failure(self) -> None:
        """Écarte le pool HTTP courant après un échec réseau Serenicity."""
        previous_session = self._session
        self._session = self._build_session()
        try:
            previous_session.close()
        except requests.RequestException as exc:
            LOGGER.debug(
                "Fermeture de session Serenicity échouée après erreur HTTP : %s",
                exc,
            )

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
