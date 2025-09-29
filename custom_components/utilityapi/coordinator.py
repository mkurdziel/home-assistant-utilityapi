from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

import logging
from homeassistant.util import dt as dt_util
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import UtilityAPIClient, UtilityAPIError
from .statistics_helper import async_write_hourly_usage_cost


class UtilityAPIDataCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Coordinator that refreshes meter summaries daily."""

    def __init__(self, hass: HomeAssistant, client: UtilityAPIClient, meter_ids: List[str], lookback_days: int = 30) -> None:
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name="UtilityAPI Meter Data",
            update_interval=timedelta(days=1),
        )
        self._client = client
        self._meter_ids = meter_ids
        self.lookback_days = lookback_days

    @property
    def meter_ids(self) -> List[str]:
        return self._meter_ids

    async def _async_update_data(self) -> Dict[str, Any]:
        try:
            results: Dict[str, Any] = {}
            # Determine last fully completed local day (dates as YYYY-MM-DD)
            now = dt_util.now()
            yesterday_date = (now - timedelta(days=1)).date()
            start_date = yesterday_date.isoformat()
            end_date = (yesterday_date + timedelta(days=1)).isoformat()
            # Lookback window to backfill delayed data
            days = max(1, min(365, int(self.lookback_days or 30)))
            lookback_start = (now.date() - timedelta(days=days)).isoformat()
            lookback_end = now.date().isoformat()

            for meter_id in self._meter_ids:
                summary = await self._client.refresh_meter_summary(meter_id)
                daily: Dict[str, Any] = {"date": str(yesterday_date)}
                hours: List[Dict[str, Any]] = []
                try:
                    # Fetch a lookback window to capture any late-posted data
                    intervals_win = await self._client.get_intervals(meter_id, lookback_start, lookback_end)
                    # Normalize intervals array
                    arr = []
                    if isinstance(intervals_win, dict) and isinstance(intervals_win.get("intervals"), list):
                        arr = intervals_win["intervals"]

                    total_val = 0.0
                    total_cost_reported = 0.0
                    unit = None
                    # Group readings by day for backfill
                    by_day: Dict[str, List[Dict[str, Any]]] = {}
                    # Each interval has 'readings': list with datapoints for that day/hour
                    for inter in arr:
                        readings = inter.get("readings") or []
                        for r in readings:
                            usage = 0.0
                            # Sum datapoints values
                            dps = r.get("datapoints") or []
                            for dp in dps:
                                v = dp.get("value")
                                try:
                                    usage += float(v)
                                except (TypeError, ValueError):
                                    pass
                                unit = unit or dp.get("unit")
                            # Cost may be at datapoint or reading level
                            cost = 0.0
                            cost_found = False
                            for dp in dps:
                                c = dp.get("cost")
                                if c is not None:
                                    try:
                                        cost += float(c)
                                        cost_found = True
                                    except (TypeError, ValueError):
                                        pass
                            c_read = r.get("cost")
                            if c_read is not None:
                                try:
                                    cost += float(c_read)
                                    cost_found = True
                                except (TypeError, ValueError):
                                    pass

                            entry = {
                                "start": r.get("start"),
                                "end": r.get("end"),
                                "usage": usage,
                                "cost": cost if cost_found else None,
                                "unit": unit,
                            }
                            # Group by the local date in start timestamp
                            s = r.get("start") or ""
                            day_key = str(s)[:10] if s else str(yesterday_date)
                            by_day.setdefault(day_key, []).append(entry)
                            # Tally for yesterday only for sensor
                            if day_key == start_date:
                                total_val += usage
                                if cost_found:
                                    total_cost_reported += cost
                                hours.append(entry)

                    daily.update(
                        {
                            "usage": total_val if total_val else None,
                            "cost": total_cost_reported if total_cost_reported else None,
                            "unit": unit,
                            "currency": "USD",
                        }
                    )
                except UtilityAPIError:
                    # If intervals are unavailable, leave unknowns
                    daily.update({"usage": None, "cost": None})

                # If no cost reported in intervals (yesterday), estimate from bills and distribute by usage
                if daily.get("cost") in (None, 0):
                    try:
                        bills = await self._client.get_bills(meter_id, start_date, end_date)
                        bill_list = []
                        if isinstance(bills, dict):
                            if isinstance(bills.get("bills"), list):
                                bill_list = bills["bills"]
                            elif isinstance(bills.get("data"), list):
                                bill_list = bills["data"]
                        # Find any bill that covers yesterday
                        est_cost = None
                        for b in bill_list:
                            period = b.get("period") or {}
                            p_start = period.get("start") or b.get("start")
                            p_end = period.get("end") or b.get("end")
                            total = b.get("total") or b.get("amount_due") or b.get("amount")
                            try:
                                total_f = float(total)
                            except (TypeError, ValueError):
                                continue
                            if p_start and p_end:
                                try:
                                    ps_dt = dt_util.parse_datetime(p_start)
                                    pe_dt = dt_util.parse_datetime(p_end)
                                except Exception:
                                    ps_dt = None
                                    pe_dt = None
                                if not ps_dt:
                                    try:
                                        ps_d = dt_util.parse_date(p_start)
                                    except Exception:
                                        ps_d = None
                                else:
                                    ps_d = ps_dt.date()
                                if not pe_dt:
                                    try:
                                        pe_d = dt_util.parse_date(p_end)
                                    except Exception:
                                        pe_d = None
                                else:
                                    pe_d = pe_dt.date()
                                if ps_d and pe_d:
                                    days = (pe_d - ps_d).days or 1
                                    if ps_d <= yesterday_date < pe_d:
                                        est_cost = total_f / days
                                        break
                        if est_cost is not None:
                            daily["cost"] = est_cost
                            # Distribute across hours proportional to usage
                            sum_usage = sum((h.get("usage") or 0) for h in hours)
                            if sum_usage > 0:
                                for h in hours:
                                    h["cost"] = est_cost * ((h.get("usage") or 0) / sum_usage)
                            else:
                                n = len(hours) or 1
                                for h in hours:
                                    h["cost"] = est_cost / n
                    except UtilityAPIError:
                        pass

                # Persist hourly statistics for lookback window (all available days)
                try:
                    for day_key, day_hours in by_day.items():
                        await async_write_hourly_usage_cost(
                            self.hass,
                            meter_id,
                            unit=daily.get("unit"),
                            currency=daily.get("currency"),
                            hours=day_hours,
                        )
                except Exception:
                    # Do not fail the update if statistics writing fails
                    pass

                results[meter_id] = {
                    **(summary if isinstance(summary, dict) else {}),
                    "daily": daily,
                    "yesterday_hours": hours,
                }

            return results
        except UtilityAPIError as err:
            raise UpdateFailed(str(err)) from err

    async def refresh_meters(self) -> List[str]:
        """Discover current non-archived meters and update our list (used on reload)."""
        meters = await self._client.list_meters(archived=False)
        self._meter_ids = [m.id for m in meters if not m.archived]
        await self.async_request_refresh()
        return self._meter_ids
