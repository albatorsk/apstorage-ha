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
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory

from . import APstorageCoordinator
from .const import DOMAIN, APSTORAGE_REGISTERS, BATTERY_ALARM_BITS, PCS_ALARM_BITS, DIAGNOSTIC_REGISTERS

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
    def entity_category(self) -> EntityCategory | None:
        """Return the entity category for diagnostic sensors."""
        if self._address in DIAGNOSTIC_REGISTERS:
            return EntityCategory.DIAGNOSTIC
        return None

    @property
    def state_class(self) -> SensorStateClass | None:
        """Return the state class for sensors that support statistics."""
        # Total increasing energy sensors
        if self._address in (40148, 40150):  # Charge/Discharge Energy (cumulative)
            return SensorStateClass.TOTAL_INCREASING
        # Total energy sensors (daily reset)
        elif self._address in (40146, 40147):  # Daily Charge/Discharge Energy
            return SensorStateClass.TOTAL
        # Measurement sensors (instantaneous values)
        elif self._device_class in ("voltage", "current", "power", "temperature", "battery"):
            return SensorStateClass.MEASUREMENT
        return None

    @property
    def state(self) -> Any:
        """Return the sensor state."""
        if self._coordinator.data and self._address in self._coordinator.data:
            value = self._coordinator.data[self._address].get("value")
            # Format bitfield values as hex for better readability
            if self._value_type == "bitfield32" and value is not None:
                return f"0x{value:08X}"
            return value
        return STATE_UNKNOWN

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes for bitfield sensors."""
        if self._value_type != "bitfield32":
            return None
            
        if not self._coordinator.data or self._address not in self._coordinator.data:
            return None
            
        bitfield_value = self._coordinator.data[self._address].get("value")
        if bitfield_value is None:
            return None
        
        # Determine which alarm bits to use based on address
        alarm_bits = {}
        if self._address == 40096:
            alarm_bits = BATTERY_ALARM_BITS
        elif self._address == 40100:
            alarm_bits = PCS_ALARM_BITS
        
        # Build attributes showing which alarms are active
        active_alarms = []
        attributes = {"raw_value": bitfield_value}
        
        for bit, name in alarm_bits.items():
            is_set = bool((bitfield_value >> bit) & 1)
            attributes[f"bit_{bit}_{name}"] = is_set
            if is_set:
                active_alarms.append(name)
        
        attributes["active_alarms"] = ", ".join(active_alarms) if active_alarms else "None"
        attributes["active_count"] = len(active_alarms)
        
        return attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._coordinator.last_update_success

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        # Try to get device info from coordinator data
        manufacturer = "APstorage"
        model = "Battery Management System"
        serial_number = None
        sw_version = None
        
        if self._coordinator.data:
            # Manufacturer from register 40004
            if 40004 in self._coordinator.data:
                mfr = self._coordinator.data[40004].get("value")
                if mfr and mfr.strip():
                    manufacturer = mfr
            
            # Model from register 40020
            if 40020 in self._coordinator.data:
                mdl = self._coordinator.data[40020].get("value")
                if mdl and mdl.strip():
                    model = mdl
            
            # Serial Number from register 40052
            if 40052 in self._coordinator.data:
                sn = self._coordinator.data[40052].get("value")
                if sn and sn.strip():
                    serial_number = sn
            
            # Software Version from register 40044
            if 40044 in self._coordinator.data:
                ver = self._coordinator.data[40044].get("value")
                if ver and ver.strip():
                    sw_version = ver
        
        device_info = DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="APstorage Battery",
            manufacturer=manufacturer,
            model=model,
            hw_version="Modbus TCP/RTU",
            configuration_url=f"http://{self._entry.data.get(CONF_HOST)}",
        )
        
        if serial_number:
            device_info["serial_number"] = serial_number
        if sw_version:
            device_info["sw_version"] = sw_version
            
        return device_info

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

