"""Utilitaires de validation et de dérivation de couleurs hexadécimales."""

from __future__ import annotations

import colorsys
import random
import re
from typing import Any


HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


def normalize_hex_color(value: str) -> str:
    """Normalise une couleur hexadécimale au format ``#RRGGBB``.

    Args:
        value: Couleur brute à normaliser.

    Returns:
        La couleur normalisée en majuscules.

    Raises:
        ValueError: Si la couleur n'est pas au format hexadécimal attendu.
    """
    normalized_value = value.strip().upper()
    if not HEX_COLOR_PATTERN.fullmatch(normalized_value):
        raise ValueError(f"Couleur hexadécimale invalide : {value}")
    return normalized_value


def require_hex_color(value: Any, field_name: str) -> str:
    """Valide une couleur obligatoire au format hexadécimal.

    Args:
        value: Valeur brute à valider.
        field_name: Nom du champ pour le message d'erreur.

    Returns:
        La couleur normalisée en majuscules.

    Raises:
        ValueError: Si la valeur n'est pas une chaîne hexadécimale valide.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Champ couleur invalide : {field_name}")
    return normalize_hex_color(value)


def derive_color_random(hex_color: str, variation: float = 0.15) -> str:
    """Génère une couleur proche d'une couleur de référence.

    Args:
        hex_color: Couleur de base au format ``#RRGGBB``.
        variation: Intensité maximale de variation entre ``0.0`` et ``1.0``.

    Returns:
        Une couleur hexadécimale proche de la couleur d'origine.

    Raises:
        ValueError: Si la couleur ou le niveau de variation sont invalides.
    """
    if variation < 0 or variation > 1:
        raise ValueError("La variation de couleur doit être comprise entre 0.0 et 1.0")

    normalized_color = normalize_hex_color(hex_color)
    red, green, blue = tuple(
        int(normalized_color[index : index + 2], 16) / 255.0
        for index in (1, 3, 5)
    )

    hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
    new_hue = (hue + random.uniform(-variation / 2, variation / 2)) % 1.0
    new_lightness = max(0.1, min(0.9, lightness + random.uniform(-variation, variation)))
    new_saturation = max(0.1, min(1.0, saturation + random.uniform(-variation, variation)))

    new_red, new_green, new_blue = colorsys.hls_to_rgb(
        new_hue,
        new_lightness,
        new_saturation,
    )
    return "#{:02X}{:02X}{:02X}".format(
        int(round(new_red * 255)),
        int(round(new_green * 255)),
        int(round(new_blue * 255)),
    )
