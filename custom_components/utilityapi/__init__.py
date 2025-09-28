from __future__ import annotations

from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_API_KEY, PLATFORMS
from .api import UtilityAPIClient
from .coordinator import UtilityAPIDataCoordinator


async def async_setup(hass: HomeAssistant, config: Dict[str, Any]) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    api_key: str = entry.data[CONF_API_KEY]
    client = UtilityAPIClient(session, api_key)

    meters = await client.list_meters(archived=False)
    meter_ids = [m.id for m in meters if not m.archived]

    coordinator = UtilityAPIDataCoordinator(hass, client, meter_ids)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    # On options update or manual reload, re-discover meters and refresh
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: UtilityAPIDataCoordinator = data["coordinator"]
    await coordinator.refresh_meters()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and entry.entry_id in hass.data.get(DOMAIN, {}):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
