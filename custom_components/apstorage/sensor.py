"""Sensor platform for APstorage Modbus integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    STATE_UNKNOWN,
)
from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import APstorageCoordinator
from .const import DOMAIN, APSTORAGE_REGISTERS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensor platform from ConfigEntry."""
    coordinator: APstorageCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = []
    for address, (name, count, value_type, scale, unit, device_class) in APSTORAGE_REGISTERS.items():
        entities.append(
            APstorageRegisterSensor(
                coordinator,
                entry,
                address,
                name,
                unit,
                device_class,
                value_type,
            )
        )

    async_add_entities(entities, True)


class APstorageRegisterSensor(SensorEntity):
    """Sensor entity for a single APstorage Modbus register."""

    def __init__(
        self,
        coordinator: APstorageCoordinator,
        entry: ConfigEntry,
        address: int,
        name: str,
        unit_of_measurement: str | None,
        device_class: str | None,
        value_type: str,
    ):
        self._coordinator = coordinator
        self._entry = entry
        self._address = address
        self._name = name
        self._unit_of_measurement = unit_of_measurement
        self._device_class = device_class
        self._value_type = value_type

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this sensor."""
        return f"apstorage_{self._entry.entry_id}_{self._address}"

    @property
    def unit_of_measurement(self) -> str | None:
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def device_class(self) -> str | None:
        """Return the device class."""
        return self._device_class

    @property
    def state(self) -> Any:
        """Return the sensor state."""
        if self._coordinator.data and self._address in self._coordinator.data:
            return self._coordinator.data[self._address].get("value")
        return STATE_UNKNOWN

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._coordinator.last_update_success

    @property
    def should_poll(self) -> bool:
        """No polling needed, coordinator updates."""
        return False

    async def async_added_to_hass(self) -> None:
        """Register with coordinator."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self) -> None:
        """Update via coordinator."""
        await self._coordinator.async_request_refresh()

