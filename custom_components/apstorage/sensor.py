"""Sensor platform for APstorage Modbus integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_UNIT,
    STATE_UNKNOWN,
)
from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from . import APstorageCoordinator
from .const import (
    DOMAIN,
    CONF_CONNECTION_TYPE,
    CONF_BAUDRATE,
    CONNECTION_TCP,
    CONNECTION_RTU,
    DEFAULT_SCAN_INTERVAL,
    APSTORAGE_REGISTERS,
)

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Optional(CONF_PORT, default=502): cv.port,
                vol.Optional(CONF_UNIT, default=1): cv.positive_int,
                vol.Optional(CONF_CONNECTION_TYPE, default=CONNECTION_TCP): vol.In(
                    [CONNECTION_TCP, CONNECTION_RTU]
                ),
                vol.Optional(CONF_BAUDRATE, default=9600): cv.positive_int,
                vol.Optional("scan_interval", default=int(DEFAULT_SCAN_INTERVAL.total_seconds())): cv.positive_int,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup_platform(
    hass: HomeAssistant, config: dict, add_entities: AddEntitiesCallback, discovery_info=None
):
    """Set up APstorage sensor platform."""
    cfg = config.get(DOMAIN, {})
    host = cfg.get(CONF_HOST)
    port = cfg.get(CONF_PORT)
    unit = cfg.get(CONF_UNIT)
    connection_type = cfg.get(CONF_CONNECTION_TYPE, CONNECTION_TCP)
    baudrate = cfg.get(CONF_BAUDRATE, 9600)
    scan_interval_seconds = cfg.get("scan_interval", 30)

    from datetime import timedelta
    scan_interval = timedelta(seconds=scan_interval_seconds)

    # Create and initialize coordinator
    coordinator = APstorageCoordinator(
        hass, host, port, unit, connection_type, scan_interval, baudrate
    )
    if not await coordinator.async_init():
        _LOGGER.error("Failed to initialize APstorage Modbus coordinator")
        return

    await coordinator.async_refresh()

    # Create sensor entities for each register
    entities: list[Entity] = []
    for address, (name, count, value_type, scale, unit_of_meas, device_class) in APSTORAGE_REGISTERS.items():
        entities.append(
            APstorageRegisterSensor(
                coordinator, address, name, unit_of_meas, device_class, value_type
            )
        )

    add_entities(entities, True)


class APstorageRegisterSensor(SensorEntity):
    """Sensor entity for a single APstorage Modbus register."""

    def __init__(
        self,
        coordinator: APstorageCoordinator,
        address: int,
        name: str,
        unit_of_measurement: str | None,
        device_class: str | None,
        value_type: str,
    ):
        self._coordinator = coordinator
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
        return f"apstorage_{self._address}"

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

