"""Number platform for APstorage Modbus integration (writable registers)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.components.number import (
    NumberEntity,
    NumberMode,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo

from . import APstorageCoordinator
from .const import DOMAIN, APSTORAGE_REGISTERS, APSTORAGE_WRITABLE_REGISTERS
from .entity_naming import async_migrate_entity_id, get_suggested_object_id

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up number platform from ConfigEntry."""
    coordinator: APstorageCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = []
    for address, meta in APSTORAGE_WRITABLE_REGISTERS.items():
        if address in APSTORAGE_REGISTERS:
            name, count, value_type, scale, unit, device_class = APSTORAGE_REGISTERS[address]
            entities.append(
                APstorageWritableNumber(
                    coordinator,
                    entry,
                    address,
                    name,
                    unit,
                    device_class,
                    value_type,
                    scale,
                    meta,
                )
            )

    async_add_entities(entities, True)


class APstorageWritableNumber(NumberEntity):
    """Number entity for a writable APstorage Modbus register."""

    def __init__(
        self,
        coordinator: APstorageCoordinator,
        entry: ConfigEntry,
        address: int,
        name: str,
        unit_of_measurement: str | None,
        device_class: str | None,
        value_type: str,
        scale: float,
        meta: dict[str, Any],
    ):
        self._coordinator = coordinator
        self._entry = entry
        self._address = address
        self._name = name
        self._unit_of_measurement = unit_of_measurement
        self._device_class = device_class
        self._value_type = value_type
        self._scale = scale
        self._min_value = float(meta.get("min", 0))
        self._max_value = float(meta.get("max", 100))
        self._step = float(meta.get("step", 1))
        self._mode = str(meta.get("mode", "box"))

    @property
    def name(self) -> str:
        """Return the name of the number."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this entity."""
        return f"apstorage_{self._entry.entry_id}_{self._address}"

    @property
    def suggested_object_id(self) -> str | None:
        """Return the preferred object ID for this number."""
        return get_suggested_object_id(self._coordinator.data, self._name)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the native unit of measurement."""
        return self._unit_of_measurement

    @property
    def device_class(self) -> str | None:
        """Return the device class."""
        return self._device_class

    @property
    def native_value(self) -> float | None:
        """Return the sensor state."""
        if self._coordinator.data and self._address in self._coordinator.data:
            return self._coordinator.data[self._address].get("value")
        return None

    @property
    def native_min_value(self) -> float:
        """Return the minimum value."""
        return self._min_value

    @property
    def native_max_value(self) -> float:
        """Return the maximum value."""
        return self._max_value

    @property
    def native_step(self) -> float:
        """Return the step size."""
        return self._step

    @property
    def mode(self) -> NumberMode:
        """Return the number mode."""
        return NumberMode.SLIDER if self._mode == "slider" else NumberMode.BOX

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

    async def async_set_native_value(self, value: float) -> None:
        """Set the register value."""
        try:
            # Convert displayed value back to raw register value.
            # Example: scale 0.1 means 85.6% is stored as 856.
            raw_value = value
            if self._scale not in (0, 1):
                raw_value = value / self._scale

            int_value = int(round(raw_value))
            success = await self._coordinator.hass.async_add_executor_job(
                self._coordinator.modbus_client.write_register, self._address, int_value
            )
            if success:
                _LOGGER.info("Set register %d to %d", self._address, int_value)
                # Request immediate refresh to update the displayed value
                await self._coordinator.async_request_refresh()
            else:
                _LOGGER.error("Failed to set register %d", self._address)
        except Exception as err:
            _LOGGER.exception("Error setting register value: %s", err)

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
