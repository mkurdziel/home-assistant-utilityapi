from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

import logging
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import UtilityAPIClient, UtilityAPIError


class UtilityAPIDataCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Coordinator that refreshes meter summaries daily."""

    def __init__(self, hass: HomeAssistant, client: UtilityAPIClient, meter_ids: List[str]) -> None:
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name="UtilityAPI Meter Data",
            update_interval=timedelta(days=1),
        )
        self._client = client
        self._meter_ids = meter_ids

    @property
    def meter_ids(self) -> List[str]:
        return self._meter_ids

    async def _async_update_data(self) -> Dict[str, Any]:
        try:
            results: Dict[str, Any] = {}
            for meter_id in self._meter_ids:
                results[meter_id] = await self._client.refresh_meter_summary(meter_id)
            return results
        except UtilityAPIError as err:
            raise UpdateFailed(str(err)) from err

    async def refresh_meters(self) -> List[str]:
        """Discover current non-archived meters and update our list (used on reload)."""
        meters = await self._client.list_meters(archived=False)
        self._meter_ids = [m.id for m in meters if not m.archived]
        await self.async_request_refresh()
        return self._meter_ids
