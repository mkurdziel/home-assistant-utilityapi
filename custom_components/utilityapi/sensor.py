from __future__ import annotations

from typing import Any, Optional

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .coordinator import UtilityAPIDataCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: UtilityAPIDataCoordinator = data["coordinator"]

    entities: list[SensorEntity] = []
    for meter_id in coordinator.meter_ids:
        entities.append(UtilityAPIMeterLastUpdateSensor(coordinator, meter_id))
        entities.append(UtilityAPIMeterDailyUsageSensor(coordinator, meter_id))
        entities.append(UtilityAPIMeterDailyCostSensor(coordinator, meter_id))
        entities.append(UtilityAPIMeterYesterdayBreakdownSensor(coordinator, meter_id))

    async_add_entities(entities)


class UtilityAPIMeterBaseSensor(CoordinatorEntity[UtilityAPIDataCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: UtilityAPIDataCoordinator, meter_id: str) -> None:
        super().__init__(coordinator)
        self._meter_id = meter_id

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


class UtilityAPIMeterLastUpdateSensor(UtilityAPIMeterBaseSensor):
    _attr_icon = "mdi:gauge"

    def __init__(self, coordinator: UtilityAPIDataCoordinator, meter_id: str) -> None:
        super().__init__(coordinator, meter_id)
        self._attr_unique_id = f"utilityapi_meter_{meter_id}_last_update"
        self._attr_name = "Last Update"

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


class UtilityAPIMeterDailyUsageSensor(UtilityAPIMeterBaseSensor):
    _attr_icon = "mdi:fire"
    _attr_name = "Daily Usage"
    _attr_state_class = "measurement"

    def __init__(self, coordinator: UtilityAPIDataCoordinator, meter_id: str) -> None:
        super().__init__(coordinator, meter_id)
        self._attr_unique_id = f"utilityapi_meter_{meter_id}_daily_usage"

    def _daily(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        meter = data.get(self._meter_id) or {}
        return meter.get("daily") or {}

    def _map_unit(self, unit: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        if not unit:
            return None, None
        u = str(unit).lower()
        # Energy
        if u in ("kwh", "kilowatthour", "kilowatt-hour"):
            return "energy", UnitOfEnergy.KILO_WATT_HOUR
        if u in ("wh", "watthour", "watt-hour"):
            return "energy", "Wh"
        if u in ("therm", "therms", "thm"):
            # No HA constant; use plain label
            return "energy", "therm"
        # Volume
        if u in ("m3", "m^3", "cubic_meter", "cubic meters", "cubic-meters"):
            return "volume", UnitOfVolume.CUBIC_METERS
        if u in ("ft3", "ft^3", "cf", "ccf", "mcf", "cubic_feet", "cubic-feet"):
            # CCF/MCF are multiples of ft^3; keep label for now
            return "volume", u
        return None, unit

    @property
    def native_value(self) -> Any:
        d = self._daily()
        return d.get("usage")

    @property
    def native_unit_of_measurement(self) -> Optional[str]:
        d = self._daily()
        _, unit = self._map_unit(d.get("unit"))
        return unit

    @property
    def device_class(self) -> Optional[str]:
        d = self._daily()
        dc, _ = self._map_unit(d.get("unit"))
        return dc

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._daily()
        return {"date": d.get("date"), "meter_id": self._meter_id}


class UtilityAPIMeterDailyCostSensor(UtilityAPIMeterBaseSensor):
    _attr_icon = "mdi:cash"
    _attr_name = "Daily Cost"
    _attr_state_class = "measurement"

    def __init__(self, coordinator: UtilityAPIDataCoordinator, meter_id: str) -> None:
        super().__init__(coordinator, meter_id)
        self._attr_unique_id = f"utilityapi_meter_{meter_id}_daily_cost"

    def _daily(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        meter = data.get(self._meter_id) or {}
        return meter.get("daily") or {}

    @property
    def native_value(self) -> Any:
        d = self._daily()
        return d.get("cost")

    @property
    def device_class(self) -> Optional[str]:
        return "monetary"

    @property
    def native_unit_of_measurement(self) -> Optional[str]:
        d = self._daily()
        return d.get("currency") or "USD"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._daily()
        return {"date": d.get("date"), "meter_id": self._meter_id}


class UtilityAPIMeterYesterdayBreakdownSensor(UtilityAPIMeterBaseSensor):
    _attr_icon = "mdi:timeline-clock"
    _attr_name = "Yesterday Breakdown"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: UtilityAPIDataCoordinator, meter_id: str) -> None:
        super().__init__(coordinator, meter_id)
        self._attr_unique_id = f"utilityapi_meter_{meter_id}_yesterday_breakdown"

    def _hours(self) -> list[dict[str, Any]]:
        data = self.coordinator.data or {}
        meter = data.get(self._meter_id) or {}
        return meter.get("yesterday_hours") or []

    @property
    def native_value(self) -> Any:
        daily = (self.coordinator.data or {}).get(self._meter_id, {}).get("daily", {})
        return daily.get("date")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "hours": self._hours(),
            "meter_id": self._meter_id,
        }
