"""Package des utilitaires partagés."""

from .color import derive_color_random, normalize_hex_color, require_hex_color
from .datetime import (
    ensure_utc_datetime,
    format_utc_datetime_for_api,
    from_database_timestamp,
    to_database_timestamp,
)
from .normalization import (
    NormalizationError,
    copy_payload,
    normalize_collected_at,
    normalize_datetime_to_utc,
    optional_float,
    optional_text,
    require_identifier,
    require_ip,
    require_mapping,
    require_text,
    to_bool,
)

__all__ = [
    "NormalizationError",
    "copy_payload",
    "ensure_utc_datetime",
    "format_utc_datetime_for_api",
    "from_database_timestamp",
    "derive_color_random",
    "normalize_hex_color",
    "normalize_collected_at",
    "normalize_datetime_to_utc",
    "optional_float",
    "optional_text",
    "require_identifier",
    "require_hex_color",
    "require_ip",
    "require_mapping",
    "require_text",
    "to_database_timestamp",
    "to_bool",
]
