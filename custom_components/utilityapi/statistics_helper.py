from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple
from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

try:
    # HA 2023.12+
    from homeassistant.components.recorder.statistics import (
        async_add_external_statistics,
        async_get_last_statistics,
    )
except Exception:  # pragma: no cover - fallback for older cores
    async_add_external_statistics = None  # type: ignore
    async_get_last_statistics = None  # type: ignore


def _parse_hour_start(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = dt_util.parse_datetime(str(value)) or dt_util.parse_date(str(value))  # type: ignore
    if hasattr(dt, "hour"):
        # Normalize to exact hour start and UTC
        if dt.tzinfo is None:
            dt = dt_util.as_utc(dt)
        else:
            dt = dt_util.as_utc(dt)
        dt = dt.replace(minute=0, second=0, microsecond=0)
        return dt
    # If only date, use midnight UTC
    d = dt  # type: ignore
    return dt_util.as_utc(datetime(d.year, d.month, d.day))  # type: ignore


async def async_write_hourly_usage_cost(
    hass: HomeAssistant,
    meter_id: str,
    unit: str | None,
    currency: str | None,
    hours: Iterable[Dict[str, Any]],
) -> None:
    """Write hourly usage and cost series as external statistics.

    - Builds cumulative sums continuing from the last stored sample.
    - Idempotent: Rewriting the same hour will update the stored value.
    """
    if async_add_external_statistics is None or async_get_last_statistics is None:
        # Recorder not available or too old; skip gracefully
        return

    # Prepare statistic ids
    usage_stat_id = f"utilityapi:{meter_id}_usage"
    cost_stat_id = f"utilityapi:{meter_id}_cost"

    # Fetch last sums to continue cumulatives
    last = await async_get_last_statistics(hass, 1, [usage_stat_id, cost_stat_id], include_sum=True)
    last_usage_sum = 0.0
    last_cost_sum = 0.0
    if usage_stat_id in last and last[usage_stat_id]:
        last_row = last[usage_stat_id][0]
        if (s := last_row.get("sum")) is not None:
            try:
                last_usage_sum = float(s)
            except (TypeError, ValueError):
                pass
    if cost_stat_id in last and last[cost_stat_id]:
        last_row = last[cost_stat_id][0]
        if (s := last_row.get("sum")) is not None:
            try:
                last_cost_sum = float(s)
            except (TypeError, ValueError):
                pass

    # Sort hours by start
    ordered = sorted(hours, key=lambda h: _parse_hour_start(h.get("start")))

    # Build metadata and rows
    usage_meta = {
        "statistic_id": usage_stat_id,
        "unit_of_measurement": unit or "",
        "has_mean": False,
        "has_sum": True,
        "name": f"UtilityAPI {meter_id} Usage",
    }
    cost_meta = {
        "statistic_id": cost_stat_id,
        "unit_of_measurement": currency or "USD",
        "has_mean": False,
        "has_sum": True,
        "name": f"UtilityAPI {meter_id} Cost",
    }

    usage_rows: List[Dict[str, Any]] = []
    cost_rows: List[Dict[str, Any]] = []

    running_usage = last_usage_sum
    running_cost = last_cost_sum

    for h in ordered:
        start = _parse_hour_start(h.get("start"))
        u = h.get("usage") or 0
        c = h.get("cost") or 0
        try:
            running_usage += float(u)
        except (TypeError, ValueError):
            pass
        try:
            running_cost += float(c)
        except (TypeError, ValueError):
            pass
        usage_rows.append({"start": start, "sum": running_usage})
        # Only write cost if known; otherwise, keep last sum to avoid artificial plateaus
        if h.get("cost") is not None:
            cost_rows.append({"start": start, "sum": running_cost})

    if usage_rows:
        await async_add_external_statistics(hass, usage_meta, usage_rows)
    if cost_rows:
        await async_add_external_statistics(hass, cost_meta, cost_rows)

