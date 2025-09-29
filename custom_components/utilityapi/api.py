from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import asyncio
import aiohttp
import asyncio
import logging

from .const import DEFAULT_BASE_URL


@dataclass
class UtilityAPIMeter:
    id: str
    archived: bool
    label: Optional[str]
    updated: Optional[str]
    raw: Dict[str, Any]


class UtilityAPIClient:
    def __init__(self, session: aiohttp.ClientSession, api_key: str, base_url: str = DEFAULT_BASE_URL) -> None:
        self._session = session
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        # A small semaphore to avoid flooding the API if many meters
        self._sem = asyncio.Semaphore(5)
        # auth_mode: 'auto' tries Bearer first then X-API-Key if unauthorized
        self._auth_mode: str = "auto"
        self._logger = logging.getLogger(__name__)

    def _headers(self, use_mode: Optional[str] = None) -> Dict[str, str]:
        mode = use_mode or ("bearer" if self._auth_mode in ("auto", "bearer") else "x-api-key")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "HomeAssistant-UtilityAPI/0.1.0",
        }
        if mode == "bearer":
            headers["Authorization"] = f"Bearer {self._api_key}"
        else:
            headers["X-Api-Key"] = self._api_key
        return headers

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self._base_url}/{path.lstrip('/') }"
        async with self._sem:
            try:
                # Try with current/primary mode
                async with self._session.get(
                    url,
                    headers=self._headers("bearer" if self._auth_mode in ("auto", "bearer") else "x-api-key"),
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status in (401, 403):
                        # If auto, retry using alternate header style once
                        if self._auth_mode == "auto":
                            alt = "x-api-key" if "Authorization" in self._headers("bearer") else "bearer"
                            self._logger.debug("UtilityAPI unauthorized with primary auth; retrying with %s", alt)
                            async with self._session.get(
                                url,
                                headers=self._headers(alt),
                                params=params,
                                timeout=aiohttp.ClientTimeout(total=30),
                            ) as resp2:
                                if resp2.status in (401, 403):
                                    raise InvalidAuthError("Invalid UtilityAPI API key")
                                if resp2.status >= 400:
                                    text2 = await resp2.text()
                                    raise UtilityAPIError(f"GET {url} failed: {resp2.status} {text2}")
                                # Lock in the working auth mode
                                self._auth_mode = alt
                                return await resp2.json()
                        raise InvalidAuthError("Invalid UtilityAPI API key")
                    if resp.status >= 400:
                        text = await resp.text()
                        raise UtilityAPIError(f"GET {url} failed: {resp.status} {text}")
                    # If we got here, request worked; set mode if auto
                    if self._auth_mode == "auto":
                        # Determine which header was used successfully
                        self._auth_mode = "bearer" if "Authorization" in self._headers("bearer") else "x-api-key"
                    return await resp.json()
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                raise UtilityAPIError(f"Network error calling {url}: {e}") from e

    async def validate(self) -> None:
        # Minimal request to validate the API key; prefer known filter param
        await self._get("meters", {"is_archived": "false"})

    async def list_meters(self, archived: Optional[bool] = None) -> List[UtilityAPIMeter]:
        params: Dict[str, Any] = {}
        if archived is not None:
            # UtilityAPI API uses 'is_archived' for filtering
            params["is_archived"] = str(archived).lower()
        data = await self._get("meters", params)
        # UtilityAPI commonly returns an object with 'meters' array; support both list or object
        meters_raw: List[Dict[str, Any]]
        if isinstance(data, dict) and "meters" in data:
            meters_raw = data["meters"] or []
        elif isinstance(data, list):
            meters_raw = data
        else:
            meters_raw = []
        meters: List[UtilityAPIMeter] = []
        for m in meters_raw:
            meters.append(
                UtilityAPIMeter(
                    id=str(m.get("id") or m.get("meter_id") or m.get("uid") or ""),
                    archived=bool(m.get("is_archived", m.get("archived", False))),
                    label=(m.get("label") or m.get("name") or m.get("service_address")),
                    updated=(m.get("updated") or m.get("modified") or m.get("updated_at")),
                    raw=m,
                )
            )
        return [m for m in meters if m.id]

    async def refresh_meter_summary(self, meter_id: str) -> Dict[str, Any]:
        """Fetch a lightweight summary for a meter to detect new data.

        We try meter metadata; if available, its 'updated' changes when new bills/intervals arrive.
        """
        # Attempt to get meter by id; if endpoint differs, fallback to list and filter
        try:
            data = await self._get(f"meters/{meter_id}")
            if isinstance(data, dict):
                return data
        except UtilityAPIError:
            pass
        # Fallback: fetch meters and filter
        meters = await self.list_meters()
        for m in meters:
            if m.id == meter_id:
                return m.raw
        return {"id": meter_id}

    async def get_intervals(
        self, meter_id: str, start_date: str, end_date: str
    ) -> Dict[str, Any]:
        """Fetch intervals for a meter between start and end dates.

        Uses the top-level intervals endpoint with `meters`, `start`, `end`.
        Dates should be YYYY-MM-DD (local) as per UtilityAPI example.
        """
        params = {
            "meters": str(meter_id),
            "start": start_date,
            "end": end_date,
        }
        return await self._get("intervals", params)

    async def get_bills(
        self, meter_id: str, start_date: str, end_date: str
    ) -> Dict[str, Any]:
        """Fetch bills overlapping the date range for a meter.

        Returns parsed JSON (dict) which may include a 'bills' list.
        """
        params = {
            "meters": str(meter_id),
            "start": start_date,
            "end": end_date,
        }
        return await self._get("bills", params)


class UtilityAPIError(Exception):
    pass


class InvalidAuthError(UtilityAPIError):
    pass
