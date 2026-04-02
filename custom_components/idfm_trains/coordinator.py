"""Coordinator for the IDFM Trains integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_API_KEY,
    CONF_LINES_FILTER,
    CONF_OUTSIDE_INTERVAL,
    CONF_STOP_AREA_ID,
    CONF_TIME_END,
    CONF_TIME_START,
    CONF_TRAIN_COUNT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_OUTSIDE_INTERVAL,
    DEFAULT_TIME_END,
    DEFAULT_TIME_START,
    DEFAULT_TRAIN_COUNT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    KNOWN_LINES,
    SIRI_DELIVERY,
    SIRI_MONITORED_CALL,
    SIRI_MONITORED_STOP,
    SIRI_ROOT,
    SIRI_STOP_DELIVERY,
    SIRI_VEHICLE_JOURNEY,
    STOP_MONITORING_URL,
)

_LOGGER = logging.getLogger(__name__)


def _parse_idfm_time(time_str: str | None) -> datetime | None:
    """Parse an ISO 8601 time string from the PRIM API."""
    if not time_str:
        return None
    try:
        # Python 3.11+ handles %z with colon, older versions may need fromisoformat
        dt = datetime.fromisoformat(time_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _get_line_id(line_ref: str | None) -> str | None:
    """Extract the line code from a STIF LineRef like 'STIF:Line::C01728:'."""
    if not line_ref:
        return None
    parts = line_ref.split(":")
    for part in reversed(parts):
        if part.startswith("C") and len(part) > 1:
            return part
    return None


def _parse_departure(visit: dict) -> dict | None:
    """Parse a single MonitoredStopVisit into a structured departure dict."""
    try:
        journey = visit.get(SIRI_VEHICLE_JOURNEY, {})
        call = journey.get(SIRI_MONITORED_CALL, {})

        line_ref_val = journey.get("LineRef", {})
        if isinstance(line_ref_val, dict):
            line_ref = line_ref_val.get("value", "")
        else:
            line_ref = str(line_ref_val)

        line_id = _get_line_id(line_ref)
        line_info = KNOWN_LINES.get(line_id, {}) if line_id else {}

        # Prefer the PublishedLineName from the API response over hardcoded names
        pub_name_val = journey.get("PublishedLineName", [])
        if pub_name_val and isinstance(pub_name_val, list):
            api_line_name = pub_name_val[0].get("value", "")
        else:
            api_line_name = ""
        line_name = line_info.get("name") or api_line_name or line_id or "?"

        # Destination
        dest_list = journey.get("DestinationName", [])
        if dest_list and isinstance(dest_list, list):
            dest = dest_list[0].get("value", "")
        else:
            dest = journey.get("DirectionName", [{}])[0].get("value", "") if journey.get("DirectionName") else ""

        # Times
        aimed_dep = _parse_idfm_time(call.get("AimedDepartureTime"))
        expected_dep = _parse_idfm_time(call.get("ExpectedDepartureTime"))
        # Fallback to arrival if departure is not available
        if aimed_dep is None:
            aimed_dep = _parse_idfm_time(call.get("AimedArrivalTime"))
        if expected_dep is None:
            expected_dep = _parse_idfm_time(call.get("ExpectedArrivalTime"))

        departure_time = expected_dep or aimed_dep
        if departure_time is None:
            return None

        # Delay in minutes
        delay_minutes = 0
        if aimed_dep and expected_dep:
            delta = expected_dep - aimed_dep
            delay_minutes = max(0, int(delta.total_seconds() / 60))

        # Platform
        platform_raw = call.get("DeparturePlatformName", {})
        if isinstance(platform_raw, dict):
            platform = platform_raw.get("value", "")
        else:
            platform = str(platform_raw) if platform_raw else ""

        # Status
        departure_status = call.get("DepartureStatus", "")

        # Train number / vehicle journey
        framed = journey.get("FramedVehicleJourneyRef", {})
        train_number = framed.get("DatedVehicleJourneyRef", "") if isinstance(framed, dict) else ""

        return {
            "line_id": line_id,
            "line_name": line_name,
            "line_color": line_info.get("color", "#888888"),
            "destination": dest,
            "aimed_departure": aimed_dep,
            "expected_departure": expected_dep,
            "departure_time": departure_time,
            "delay_minutes": delay_minutes,
            "platform": platform,
            "departure_status": departure_status,
            "train_number": train_number,
        }
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("Failed to parse MonitoredStopVisit: %s", exc)
        return None


class IdfmTrainsCoordinator(DataUpdateCoordinator):
    """Coordinates data fetching from the PRIM SIRI Lite API."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self._api_key = entry.data[CONF_API_KEY]
        self._stop_area_id = entry.data[CONF_STOP_AREA_ID]

        # Options (may be updated without restart)
        # ⚠️  Ne pas utiliser self._update_interval : nom réservé par DataUpdateCoordinator
        opts = entry.options
        self._train_count: int = int(opts.get(CONF_TRAIN_COUNT, DEFAULT_TRAIN_COUNT))
        self._lines_filter: list[str] = opts.get(CONF_LINES_FILTER, [])
        self._active_interval_min: int = int(opts.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
        self._inactive_interval_min: int = int(opts.get(CONF_OUTSIDE_INTERVAL, DEFAULT_OUTSIDE_INTERVAL))
        self._time_start: str = opts.get(CONF_TIME_START, DEFAULT_TIME_START)
        self._time_end: str = opts.get(CONF_TIME_END, DEFAULT_TIME_END)

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self._stop_area_id}",
            update_interval=self._compute_interval(),
        )

    def _compute_interval(self) -> timedelta:
        """Calcule l'intervalle adapté selon l'heure courante."""
        from datetime import time as dtime
        now = dt_util.now().time()
        try:
            h_start, m_start = map(int, self._time_start.split(":"))
            h_end,   m_end   = map(int, self._time_end.split(":"))
        except (ValueError, AttributeError):
            return timedelta(minutes=self._active_interval_min)

        t_end   = dtime(h_end, m_end)
        # Activation 30 min avant le début de la plage
        pre_min = m_start - 30
        pre_h   = h_start if pre_min >= 0 else max(0, h_start - 1)
        pre_min = pre_min if pre_min >= 0 else pre_min + 60
        t_pre   = dtime(pre_h, pre_min)

        if t_pre <= now <= t_end:
            return timedelta(minutes=self._active_interval_min)
        return timedelta(minutes=self._inactive_interval_min)

    def update_options(self) -> None:
        """Recharge les options depuis la config entry (appelé après une mise à jour des options)."""
        opts = self.entry.options
        self._train_count          = int(opts.get(CONF_TRAIN_COUNT, DEFAULT_TRAIN_COUNT))
        self._lines_filter         = opts.get(CONF_LINES_FILTER, [])
        self._active_interval_min  = int(opts.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
        self._inactive_interval_min = int(opts.get(CONF_OUTSIDE_INTERVAL, DEFAULT_OUTSIDE_INTERVAL))
        self._time_start           = opts.get(CONF_TIME_START, DEFAULT_TIME_START)
        self._time_end             = opts.get(CONF_TIME_END, DEFAULT_TIME_END)
        self.update_interval       = self._compute_interval()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from PRIM API and parse it."""
        # Ajuste l'intervalle dynamiquement à chaque appel
        self.update_interval = self._compute_interval()

        monitoring_ref = f"STIF:StopArea:SP:{self._stop_area_id}:"
        params = {"MonitoringRef": monitoring_ref}

        headers = {
            "apiKey": self._api_key,
            "Accept": "application/json",
        }

        session = async_get_clientsession(self.hass)

        try:
            async with session.get(
                STOP_MONITORING_URL,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 401:
                    raise UpdateFailed("Clé API PRIM invalide ou expirée (HTTP 401)")
                if resp.status == 429:
                    raise UpdateFailed("Quota API PRIM dépassé (HTTP 429)")
                if resp.status != 200:
                    raise UpdateFailed(f"Erreur API PRIM : HTTP {resp.status}")
                raw = await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            raise UpdateFailed(f"Erreur réseau : {exc}") from exc

        return self._parse_response(raw)

    def _parse_response(self, raw: dict) -> dict[str, Any]:
        """Parse the SIRI Lite JSON response."""
        try:
            service_delivery = raw[SIRI_ROOT][SIRI_DELIVERY]
            stop_deliveries = service_delivery.get(SIRI_STOP_DELIVERY, [])
        except (KeyError, TypeError) as exc:
            raise UpdateFailed(f"Format de réponse PRIM inattendu : {exc}") from exc

        all_visits: list[dict] = []
        for delivery in stop_deliveries:
            visits = delivery.get(SIRI_MONITORED_STOP, [])
            all_visits.extend(visits)

        departures: list[dict] = []
        now = datetime.now(tz=timezone.utc)

        # Collect line metadata dynamically from the response
        discovered_lines: dict[str, dict] = {}

        for visit in all_visits:
            dep = _parse_departure(visit)
            if dep is None:
                continue
            if dep["departure_time"] < now - timedelta(minutes=1):
                continue
            if self._lines_filter and dep["line_id"] not in self._lines_filter:
                continue
            departures.append(dep)

            # Enrich discovered lines with published name from API
            lid = dep["line_id"]
            if lid and lid not in discovered_lines:
                discovered_lines[lid] = {
                    "name": dep["line_name"],
                    "color": dep["line_color"],
                }

        departures.sort(key=lambda d: d["departure_time"])

        # Merge with static KNOWN_LINES (static takes priority for name/color)
        for lid, info in KNOWN_LINES.items():
            if lid not in discovered_lines:
                discovered_lines[lid] = info

        # Group by line
        by_line: dict[str, list[dict]] = {}
        for dep in departures:
            lid = dep["line_id"] or "unknown"
            by_line.setdefault(lid, []).append(dep)

        return {
            "departures": departures[: self._train_count * 2],
            "by_line": {k: v[: self._train_count] for k, v in by_line.items()},
            "discovered_lines": discovered_lines,
            "last_update": dt_util.now().isoformat(),
            "stop_area_id": self._stop_area_id,
        }
