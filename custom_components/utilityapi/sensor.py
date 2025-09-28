from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import UtilityAPIDataCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: UtilityAPIDataCoordinator = data["coordinator"]

    entities: list[UtilityAPIMeterSensor] = []
    for meter_id in coordinator.meter_ids:
        entities.append(UtilityAPIMeterSensor(coordinator, meter_id))

    async_add_entities(entities)


class UtilityAPIMeterSensor(CoordinatorEntity[UtilityAPIDataCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:gauge"

    def __init__(self, coordinator: UtilityAPIDataCoordinator, meter_id: str) -> None:
        super().__init__(coordinator)
        self._meter_id = meter_id
        self._attr_unique_id = f"utilityapi_meter_{meter_id}_last_update"
        self._attr_name = "Last Update"

    @property
    def device_info(self) -> DeviceInfo:
        summary = self._get_summary()
        name = summary.get("label") or summary.get("name") or f"Meter {self._meter_id}"
        return DeviceInfo(
            identifiers={(DOMAIN, self._meter_id)},
            name=name,
            manufacturer="UtilityAPI",
            model=str(summary.get("utility") or summary.get("service") or "Meter"),
        )

    def _get_summary(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        summary = data.get(self._meter_id) or {}
        # Some endpoints may nest under 'meter'
        if isinstance(summary, dict) and "meter" in summary and isinstance(summary["meter"], dict):
            return summary["meter"]
        return summary

    @property
    def native_value(self) -> Any:
        summary = self._get_summary()
        return summary.get("updated") or summary.get("modified") or summary.get("updated_at")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        summary = self._get_summary()
        attrs: dict[str, Any] = {
            "meter_id": self._meter_id,
            "archived": summary.get("archived"),
        }
        # Pass through some useful known fields if present
        for key in ("label", "service_address", "utility", "account_number", "service_id"):
            if key in summary:
                attrs[key] = summary[key]
        return attrs

