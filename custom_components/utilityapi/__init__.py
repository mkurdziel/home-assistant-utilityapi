from __future__ import annotations

from typing import Any, Dict, List

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import logging
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util
from datetime import timedelta
import voluptuous as vol

from .const import DOMAIN, CONF_API_KEY, PLATFORMS, CONF_LOOKBACK_DAYS, DEFAULT_LOOKBACK_DAYS
from .api import UtilityAPIClient
from .coordinator import UtilityAPIDataCoordinator
from .statistics_helper import async_write_hourly_usage_cost

SERVICE_IMPORT_HISTORY = "import_history"
IMPORT_SCHEMA = vol.Schema(
    {
        vol.Required("meter_id"): str,
        vol.Required("start"): str,  # YYYY-MM-DD
        vol.Required("end"): str,    # YYYY-MM-DD (exclusive)
    }
)


async def async_setup(hass: HomeAssistant, config: Dict[str, Any]) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    api_key: str = entry.data[CONF_API_KEY]
    client = UtilityAPIClient(session, api_key)

    meters = await client.list_meters(archived=False)
    meter_ids = [m.id for m in meters if not m.archived]

    lookback_days = entry.options.get(CONF_LOOKBACK_DAYS, DEFAULT_LOOKBACK_DAYS)
    coordinator = UtilityAPIDataCoordinator(hass, client, meter_ids, lookback_days=lookback_days)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    async def _handle_import(call):
        logger = logging.getLogger(__name__)
        try:
            data = IMPORT_SCHEMA(call.data)
            meter_id: str = data["meter_id"]
            start_s: str = data["start"]
            end_s: str = data["end"]
            # Parse to dates
            start_d = dt_util.parse_date(start_s)
            end_d = dt_util.parse_date(end_s)
            if not start_d or not end_d:
                raise HomeAssistantError("Invalid start/end date format; expected YYYY-MM-DD")
            day = start_d
            while day < end_d:
                day_next = day + timedelta(days=1)
                # Fetch intervals for the day
                intervals = await client.get_intervals(meter_id, day.isoformat(), day_next.isoformat())
                arr = []
                if isinstance(intervals, dict) and isinstance(intervals.get("intervals"), list):
                    arr = intervals["intervals"]
                hours: List[Dict[str, Any]] = []
                unit = None
                for inter in arr:
                    readings = inter.get("readings") or []
                    for r in readings:
                        usage = 0.0
                        dps = r.get("datapoints") or []
                        for dp in dps:
                            v = dp.get("value")
                            try:
                                usage += float(v)
                            except (TypeError, ValueError):
                                pass
                            unit = unit or dp.get("unit")
                        # Cost not always present; leave None and let bills handle user-visible cost
                        hours.append(
                            {
                                "start": r.get("start"),
                                "end": r.get("end"),
                                "usage": usage,
                                "cost": None,
                                "unit": unit,
                            }
                        )
                # Write statistics for this day
                await async_write_hourly_usage_cost(hass, meter_id, unit=unit, currency="USD", hours=hours)
                day = day_next
        except HomeAssistantError:
            raise
        except Exception as err:
            logger.exception("Import history service failed: %s", err)
            raise HomeAssistantError(f"Import failed: {err}")

    hass.services.async_register(DOMAIN, SERVICE_IMPORT_HISTORY, _handle_import, schema=IMPORT_SCHEMA)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    # On options update or manual reload, re-discover meters and refresh
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: UtilityAPIDataCoordinator = data["coordinator"]
    # Update lookback days from options if changed
    coordinator.lookback_days = entry.options.get(CONF_LOOKBACK_DAYS, DEFAULT_LOOKBACK_DAYS)
    await coordinator.refresh_meters()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and entry.entry_id in hass.data.get(DOMAIN, {}):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
