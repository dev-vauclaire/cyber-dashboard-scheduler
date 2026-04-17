"""Package des clients pour les API externes."""

from .ogo_client import OgoApiClient, OgoJournalFetchResult
from .serenicity_base_client import ApiClientError
from .serenicity_lurio_client import (
    SerenicityLurioClient,
    SerenicityLurioReportFetchResult,
)
from .serenicity_sensor_client import (
    SerenicitySensorClient,
    SerenicitySensorFluxFetchResult,
)

__all__ = [
    "ApiClientError",
    "OgoApiClient",
    "OgoJournalFetchResult",
    "SerenicityLurioClient",
    "SerenicityLurioReportFetchResult",
    "SerenicitySensorClient",
    "SerenicitySensorFluxFetchResult",
]
