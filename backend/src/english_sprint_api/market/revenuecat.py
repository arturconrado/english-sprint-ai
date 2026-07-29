from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import httpx

from english_sprint_api.config import Settings

REVENUECAT_V1 = "https://api.revenuecat.com/v1"


class BillingProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EntitlementSnapshot:
    status: str
    period_ends_at: datetime | None


class EntitlementProvider(Protocol):
    async def get_entitlement(self, app_user_id: str) -> EntitlementSnapshot: ...


class RevenueCatEntitlementProvider:
    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = (
            settings.revenuecat_secret_api_key.get_secret_value()
            if settings.revenuecat_secret_api_key
            else ""
        )
        self._entitlement = settings.revenuecat_entitlement_id
        self._client = client

    async def get_entitlement(self, app_user_id: str) -> EntitlementSnapshot:
        if not self._api_key:
            raise BillingProviderError("RevenueCat is not configured.")
        if self._client is None:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await self._request(client, app_user_id)
        else:
            response = await self._request(self._client, app_user_id)
        if response.status_code >= 500:
            raise BillingProviderError("RevenueCat is temporarily unavailable.")
        if response.status_code >= 400:
            raise BillingProviderError("RevenueCat rejected the subscriber lookup.")
        payload: dict[str, Any] = response.json()
        entitlements = payload.get("subscriber", {}).get("entitlements", {})
        entitlement = entitlements.get(self._entitlement)
        if not isinstance(entitlement, dict):
            return EntitlementSnapshot("inactive", None)
        expiration = entitlement.get("expires_date")
        period_ends_at = (
            datetime.fromisoformat(expiration.replace("Z", "+00:00"))
            if isinstance(expiration, str)
            else None
        )
        return EntitlementSnapshot("active", period_ends_at)

    async def _request(
        self,
        client: httpx.AsyncClient,
        app_user_id: str,
    ) -> httpx.Response:
        return await client.get(
            f"{REVENUECAT_V1}/subscribers/{app_user_id}",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "application/json",
            },
        )
