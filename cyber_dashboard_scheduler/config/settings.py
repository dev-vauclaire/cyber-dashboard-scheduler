"""Paramètres applicatifs chargés depuis les variables d'environnement."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ENV_FILE_PATH = Path(__file__).resolve().parents[2] / ".env"
VALID_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


class ConfigurationError(ValueError):
    """Levée quand la configuration du scheduler est absente ou invalide."""


def _load_env_file() -> None:
    """Charge le fichier ``.env`` du scheduler si présent."""
    load_dotenv(dotenv_path=ENV_FILE_PATH, override=False)


def _require_env(name: str) -> str:
    """Lit une variable d'environnement obligatoire non vide.

    Args:
        name: Nom de la variable à lire.

    Returns:
        La valeur nettoyée de la variable.

    Raises:
        ConfigurationError: Si la variable est absente ou vide.
    """
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ConfigurationError(
            f"Variable d'environnement obligatoire manquante : {name}"
        )
    return value.strip()


def _require_positive_int(name: str) -> int:
    """Lit une variable d'environnement entière strictement positive.

    Args:
        name: Nom de la variable à lire.

    Returns:
        La valeur convertie en entier.

    Raises:
        ConfigurationError: Si la valeur est absente, invalide ou non positive.
    """
    value = _require_env(name)

    try:
        parsed_value = int(value)
    except ValueError as exc:
        raise ConfigurationError(
            f"Valeur entière invalide pour la variable d'environnement {name} : {value}"
        ) from exc

    if parsed_value <= 0:
        raise ConfigurationError(
            f"La variable d'environnement {name} doit être un entier positif"
        )

    return parsed_value


def _require_log_level(name: str) -> str:
    """Lit et valide un niveau de log autorisé.

    Args:
        name: Nom de la variable à lire.

    Returns:
        Le niveau de log normalisé en majuscules.

    Raises:
        ConfigurationError: Si le niveau demandé n'est pas supporté.
    """
    value = _require_env(name).upper()
    if value not in VALID_LOG_LEVELS:
        allowed_values = ", ".join(sorted(VALID_LOG_LEVELS))
        raise ConfigurationError(
            f"Niveau de log invalide pour la variable d'environnement {name} : {value}. "
            f"Valeurs attendues : {allowed_values}"
        )
    return value


def _get_positive_float(name: str, default: float) -> float:
    """Lit un flottant strictement positif avec valeur par défaut.

    Args:
        name: Nom de la variable à lire.
        default: Valeur à utiliser si la variable est absente.

    Returns:
        La valeur configurée ou la valeur par défaut.

    Raises:
        ConfigurationError: Si la valeur fournie est invalide ou non positive.
    """
    value = os.getenv(name)
    if value is None or not value.strip():
        return default

    try:
        parsed_value = float(value)
    except ValueError as exc:
        raise ConfigurationError(
            f"Valeur décimale invalide pour la variable d'environnement {name} : {value}"
        ) from exc

    if parsed_value <= 0:
        raise ConfigurationError(
            f"La variable d'environnement {name} doit être un nombre strictement positif"
        )

    return parsed_value


def _get_positive_int(name: str, default: int) -> int:
    """Lit un entier strictement positif avec valeur par défaut.

    Args:
        name: Nom de la variable à lire.
        default: Valeur à utiliser si la variable est absente.

    Returns:
        La valeur configurée ou la valeur par défaut.

    Raises:
        ConfigurationError: Si la valeur fournie est invalide ou non positive.
    """
    value = os.getenv(name)
    if value is None or not value.strip():
        return default

    try:
        parsed_value = int(value)
    except ValueError as exc:
        raise ConfigurationError(
            f"Valeur entière invalide pour la variable d'environnement {name} : {value}"
        ) from exc

    if parsed_value <= 0:
        raise ConfigurationError(
            f"La variable d'environnement {name} doit être un entier positif"
        )

    return parsed_value


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    """Paramètres de connexion à la base PostgreSQL."""

    host: str
    port: int
    name: str
    user: str
    password: str


@dataclass(frozen=True, slots=True)
class OgoSettings:
    """Configuration de l'API OGO."""

    base_url: str
    username: str
    api_key: str
    site_name_or_id: str


@dataclass(frozen=True, slots=True)
class SerenicitySettings:
    """Configuration de l'API Serenicity."""

    base_url: str
    api_key: str


@dataclass(frozen=True, slots=True)
class Settings:
    """Objet racine de configuration du scheduler."""

    database: DatabaseSettings
    limit_request_per_day: int
    log_level: str
    http_timeout_seconds: float
    poll_safety_window_seconds: int
    ogo: OgoSettings
    serenicity: SerenicitySettings

    @classmethod
    def from_env(cls) -> "Settings":
        """Construit la configuration à partir des variables d'environnement.

        Returns:
            La configuration complète du scheduler.

        Raises:
            ConfigurationError: Si une variable obligatoire est absente ou invalide.
        """
        _load_env_file()

        return cls(
            database=DatabaseSettings(
                host=_require_env("DB_HOST"),
                port=_require_positive_int("DB_PORT"),
                name=_require_env("DB_NAME"),
                user=_require_env("DB_USER"),
                password=_require_env("DB_PASSWORD"),
            ),
            limit_request_per_day=_require_positive_int("LIMIT_REQUEST_PER_DAY"),
            log_level=_require_log_level("LOG_LEVEL"),
            http_timeout_seconds=_get_positive_float("HTTP_TIMEOUT_SECONDS", 10.0),
            poll_safety_window_seconds=_get_positive_int(
                "POLL_SAFETY_WINDOW_SECONDS",
                300,
            ),
            ogo=OgoSettings(
                base_url=_require_env("OGO_BASE_URL"),
                username=_require_env("OGO_USERNAME"),
                api_key=_require_env("OGO_API_KEY"),
                site_name_or_id=_require_env("OGO_SITE_NAME_OR_ID"),
            ),
            serenicity=SerenicitySettings(
                base_url=_require_env("SERENICITY_BASE_URL"),
                api_key=_require_env("SERENICITY_API_KEY"),
            ),
        )
