from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import asyncio
import aiohttp

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

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "HomeAssistant-UtilityAPI/0.1.0",
        }

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self._base_url}/{path.lstrip('/') }"
        async with self._sem:
            async with self._session.get(url, headers=self._headers(), params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status in (401, 403):
                    raise InvalidAuthError("Invalid UtilityAPI API key")
                if resp.status >= 400:
                    text = await resp.text()
                    raise UtilityAPIError(f"GET {url} failed: {resp.status} {text}")
                return await resp.json()

    async def validate(self) -> None:
        # Minimal request to validate the API key
        # Query meters with a small limit; if unauthorized, this will raise
        await self._get("meters", {"limit": 1})

    async def list_meters(self, archived: Optional[bool] = None) -> List[UtilityAPIMeter]:
        params: Dict[str, Any] = {"limit": 500}
        if archived is not None:
            # UtilityAPI uses 'archived' boolean filter; fallback if API differs
            params["archived"] = str(archived).lower()
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
                    archived=bool(m.get("archived", False)),
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


class UtilityAPIError(Exception):
    pass


class InvalidAuthError(UtilityAPIError):
    pass
