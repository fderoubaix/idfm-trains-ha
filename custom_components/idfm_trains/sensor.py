"""Sensor platform for IDFM Trains."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_STOP_NAME,
    CONF_TRAIN_COUNT,
    DEFAULT_STOP_NAME,
    DEFAULT_TRAIN_COUNT,
    DOMAIN,
    KNOWN_LINES,
)
from .coordinator import IdfmTrainsCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IDFM Trains sensor entities."""
    coordinator: IdfmTrainsCoordinator = hass.data[DOMAIN][entry.entry_id]
    stop_name: str = entry.data.get(CONF_STOP_NAME, DEFAULT_STOP_NAME)
    train_count: int = entry.options.get(CONF_TRAIN_COUNT, DEFAULT_TRAIN_COUNT)

    # Use lines discovered from the first API response, fall back to KNOWN_LINES
    discovered = (coordinator.data or {}).get("discovered_lines", KNOWN_LINES)
    lines_to_create = discovered if discovered else KNOWN_LINES

    entities: list[SensorEntity] = []
    entities.append(IdfmMainSensor(coordinator, entry, stop_name))

    for line_id, line_info in lines_to_create.items():
        for idx in range(1, train_count + 1):
            entities.append(
                IdfmTrainSensor(coordinator, entry, stop_name, line_id, line_info, idx)
            )

    async_add_entities(entities, True)


def _device_info(entry: ConfigEntry, stop_name: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"IDFM – {stop_name}",
        manufacturer="Île-de-France Mobilités",
        model="PRIM SIRI Lite API",
        entry_type="service",
    )


class IdfmMainSensor(CoordinatorEntity[IdfmTrainsCoordinator], SensorEntity):
    """Summary sensor: shows number of next departures available."""

    _attr_icon = "mdi:train"

    def __init__(
        self,
        coordinator: IdfmTrainsCoordinator,
        entry: ConfigEntry,
        stop_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._stop_name = stop_name
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_main"
        self._attr_name = f"IDFM {stop_name}"
        self._attr_device_info = _device_info(entry, stop_name)

    @property
    def native_value(self) -> int:
        """Return the total number of upcoming departures."""
        if self.coordinator.data is None:
            return 0
        return len(self.coordinator.data.get("departures", []))

    @property
    def native_unit_of_measurement(self) -> str:
        return "trains"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        departures = data.get("departures", [])
        by_line = data.get("by_line", {})

        summary = {}
        for line_id, line_info in KNOWN_LINES.items():
            next_dep = (by_line.get(line_id) or [{}])[0]
            if next_dep:
                dt: datetime | None = next_dep.get("departure_time")
                summary[line_info["name"]] = {
                    "prochain_depart": dt.isoformat() if dt else None,
                    "destination": next_dep.get("destination"),
                    "retard_minutes": next_dep.get("delay_minutes", 0),
                }

        return {
            "gare": self._stop_name,
            "derniere_mise_a_jour": data.get("last_update"),
            "total_departs": len(departures),
            "par_ligne": summary,
        }


class IdfmTrainSensor(CoordinatorEntity[IdfmTrainsCoordinator], SensorEntity):
    """Individual train sensor (e.g. RER A – Train 2)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:train"

    def __init__(
        self,
        coordinator: IdfmTrainsCoordinator,
        entry: ConfigEntry,
        stop_name: str,
        line_id: str,
        line_info: dict,
        index: int,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._stop_name = stop_name
        self._line_id = line_id
        self._line_info = line_info
        self._index = index  # 1-based

        safe_line = line_info["name"].replace(" ", "_").lower()
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{line_id}_{index}"
        self._attr_name = f"IDFM {stop_name} – {line_info['name']} Train {index}"
        self._attr_device_info = _device_info(entry, stop_name)

    def _get_departure(self) -> dict | None:
        data = self.coordinator.data or {}
        by_line = data.get("by_line", {})
        trains = by_line.get(self._line_id, [])
        if len(trains) >= self._index:
            return trains[self._index - 1]
        return None

    @property
    def native_value(self) -> datetime | None:
        """Return the expected departure datetime (used as timestamp state)."""
        dep = self._get_departure()
        if dep is None:
            return None
        return dep.get("expected_departure") or dep.get("aimed_departure")

    @property
    def available(self) -> bool:
        return super().available and self._get_departure() is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        dep = self._get_departure()
        if dep is None:
            return {"disponible": False}

        aimed: datetime | None = dep.get("aimed_departure")
        expected: datetime | None = dep.get("expected_departure")

        return {
            "ligne": dep.get("line_name"),
            "ligne_id": dep.get("line_id"),
            "couleur_ligne": dep.get("line_color"),
            "destination": dep.get("destination"),
            "heure_theorique": aimed.isoformat() if aimed else None,
            "heure_prevue": expected.isoformat() if expected else None,
            "retard_minutes": dep.get("delay_minutes", 0),
            "quai": dep.get("platform"),
            "statut": dep.get("departure_status"),
            "numero_train": dep.get("train_number"),
            "disponible": True,
        }
