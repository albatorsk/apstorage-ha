"""Binary sensor platform for APstorage Modbus integration (alarm bitfields)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory

from . import APstorageCoordinator
from .const import DOMAIN, BATTERY_ALARM_BITS, PCS_ALARM_BITS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up binary sensor platform from ConfigEntry."""
    coordinator: APstorageCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = []
    
    # Battery Event 1 Bitfield (address 40096)
    for bit, name in BATTERY_ALARM_BITS.items():
        entities.append(
            APstorageAlarmBinarySensor(
                coordinator,
                entry,
                40096,
                bit,
                f"Battery Alarm: {name}",
                "battery_alarm",
            )
        )
    
    # PCS Alarm Bitfield (address 40100)
    for bit, name in PCS_ALARM_BITS.items():
        entities.append(
            APstorageAlarmBinarySensor(
                coordinator,
                entry,
                40100,
                bit,
                f"PCS Alarm: {name}",
                "pcs_alarm",
            )
        )

    async_add_entities(entities, True)


class APstorageAlarmBinarySensor(BinarySensorEntity):
    """Binary sensor for individual alarm bits in bitfield registers."""

    def __init__(
        self,
        coordinator: APstorageCoordinator,
        entry: ConfigEntry,
        register_address: int,
        bit_number: int,
        name: str,
        alarm_type: str,
    ):
        self._coordinator = coordinator
        self._entry = entry
        self._register_address = register_address
        self._bit_number = bit_number
        self._name = name
        self._alarm_type = alarm_type

    @property
    def name(self) -> str:
        """Return the name of the binary sensor."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this binary sensor."""
        return f"apstorage_{self._entry.entry_id}_{self._register_address}_bit{self._bit_number}"

    @property
    def device_class(self) -> str | None:
        """Return the device class."""
        return BinarySensorDeviceClass.PROBLEM

    @property
    def entity_category(self) -> EntityCategory | None:
        """Return the entity category."""
        return EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool | None:
        """Return true if the alarm bit is set."""
        if self._coordinator.data and self._register_address in self._coordinator.data:
            bitfield_value = self._coordinator.data[self._register_address].get("value")
            if bitfield_value is not None:
                return bool((bitfield_value >> self._bit_number) & 1)
        return None

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

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled by default."""
        # Disable by default to avoid cluttering the UI
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
