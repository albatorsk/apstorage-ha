"""Binary sensor platform for APstorage Modbus integration (alarm bitfields)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from . import APstorageCoordinator
from .const import DOMAIN, BATTERY_ALARM_BITS, LOGGER_NAME, PCS_ALARM_BITS
from .entity_base import APstorageEntityMixin
from .entity_naming import async_migrate_entity_id, get_suggested_object_id

_LOGGER = logging.getLogger(LOGGER_NAME)


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


class APstorageAlarmBinarySensor(APstorageEntityMixin, BinarySensorEntity):
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
    def suggested_object_id(self) -> str | None:
        """Return the preferred object ID for this binary sensor."""
        return get_suggested_object_id(self._coordinator.data, self._name)

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

        self._async_ensure_prefixed_entity_id()

    def _async_ensure_prefixed_entity_id(self) -> None:
        """Rename the entity once the device serial number is available."""
        try:
            async_migrate_entity_id(
                self.hass,
                self.entity_id,
                self._coordinator.data,
                self._name,
            )
        except ValueError:
            _LOGGER.warning("Unable to rename entity %s", self.entity_id)

    async def async_update(self) -> None:
        """Update via coordinator."""
        await self._coordinator.async_request_refresh()
        self._async_ensure_prefixed_entity_id()
