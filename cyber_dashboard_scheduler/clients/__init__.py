"""Package des clients pour les API externes."""

from .ogo_client import OgoApiClient, OgoJournalFetchResult
from .serenicity_client import ApiClientError, SerenicityApiClient

__all__ = [
    "ApiClientError",
    "OgoApiClient",
    "OgoJournalFetchResult",
    "SerenicityApiClient",
]
