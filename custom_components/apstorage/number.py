"""Number platform for APstorage Modbus integration (writable registers)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.components.number import (
    NumberEntity,
    NumberMode,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from . import APstorageCoordinator
from .const import (
    DOMAIN,
    APSTORAGE_REGISTERS,
    APSTORAGE_READONLY_NUMBER_REGISTERS,
    APSTORAGE_SCALE_REGISTERS,
    APSTORAGE_WRITABLE_REGISTERS,
    DIAGNOSTIC_REGISTERS,
    LOGGER_NAME,
)
from .entity_base import APstorageEntityMixin
from .entity_naming import async_migrate_entity_id, get_suggested_object_id

_LOGGER = logging.getLogger(LOGGER_NAME)


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

    for address in APSTORAGE_READONLY_NUMBER_REGISTERS:
        if address in APSTORAGE_REGISTERS:
            name, count, value_type, scale, unit, device_class = APSTORAGE_REGISTERS[address]
            entities.append(
                APstorageReadonlyNumber(
                    coordinator,
                    entry,
                    address,
                    name,
                    unit,
                    device_class,
                )
            )

    async_add_entities(entities, True)


class APstorageReadonlyNumber(APstorageEntityMixin, NumberEntity):
    """Number entity for read-only APstorage registers that should be numeric entities."""

    def __init__(
        self,
        coordinator: APstorageCoordinator,
        entry: ConfigEntry,
        address: int,
        name: str,
        unit_of_measurement: str | None,
        device_class: str | None,
    ):
        self._coordinator = coordinator
        self._entry = entry
        self._address = address
        self._name = name
        self._unit_of_measurement = unit_of_measurement
        self._device_class = device_class

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
    def entity_category(self) -> EntityCategory | None:
        """Return the entity category for diagnostic entities."""
        if self._address in DIAGNOSTIC_REGISTERS:
            return EntityCategory.DIAGNOSTIC
        return None

    @property
    def native_value(self) -> float | None:
        """Return the current numeric value."""
        if self._coordinator.data and self._address in self._coordinator.data:
            value = self._coordinator.data[self._address].get("value")
            if isinstance(value, (int, float)):
                return float(value)
        return None

    @property
    def native_min_value(self) -> float:
        """Return a broad min bound required by number entities."""
        return 0

    @property
    def native_max_value(self) -> float:
        """Return a broad max bound required by number entities."""
        return 65535

    @property
    def native_step(self) -> float:
        """Return the step size for number entities."""
        return 1

    @property
    def mode(self) -> NumberMode:
        """Return number mode."""
        return NumberMode.BOX

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._coordinator.last_update_success

    @property
    def should_poll(self) -> bool:
        """No polling needed, coordinator updates."""
        return False

    async def async_set_native_value(self, value: float) -> None:
        """Prevent writes for read-only numeric entities."""
        raise HomeAssistantError(f"Register {self._address} is read-only")

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


class APstorageWritableNumber(APstorageEntityMixin, NumberEntity):
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
        if self._address == 40183 and self._coordinator.data:
            max_charge = self._coordinator.data.get(40074, {}).get("value")
            # Only trust dynamic limits when they are sane positive values.
            if isinstance(max_charge, (int, float)) and max_charge > 0:
                return -float(max_charge)
        return self._min_value

    @property
    def native_max_value(self) -> float:
        """Return the maximum value."""
        if self._address == 40183 and self._coordinator.data:
            max_discharge = self._coordinator.data.get(40075, {}).get("value")
            # Only trust dynamic limits when they are sane positive values.
            if isinstance(max_discharge, (int, float)) and max_discharge > 0:
                return float(max_discharge)
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
    def entity_registry_enabled_default(self) -> bool:
        """Expose writable controls by default in Home Assistant."""
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes for writable control entities."""
        if self._address == 40183:
            return {
                "sign_convention": "positive=discharge, negative=charge, zero=standby",
            }
        return None

    @property
    def should_poll(self) -> bool:
        """No polling needed, coordinator updates."""
        return False

    async def async_set_native_value(self, value: float) -> None:
        """Set the register value."""
        try:
            effective_scale = self._scale
            scale_reg = APSTORAGE_SCALE_REGISTERS.get(self._address)
            if scale_reg is not None and self._coordinator.data and scale_reg in self._coordinator.data:
                sf = self._coordinator.data[scale_reg].get("value")
                if sf is not None:
                    effective_scale = 10 ** int(sf)

            # Convert displayed value back to raw register value.
            # Example: scale 0.1 means 85.6% is stored as 856.
            raw_value = value
            if effective_scale not in (0, 1):
                raw_value = value / effective_scale

            int_value = int(round(raw_value))

            _LOGGER.debug(
                "Set Power write requested: value=%s effective_scale=%s raw=%s int=%s range=%s..%s",
                value,
                effective_scale,
                raw_value,
                int_value,
                self.native_min_value,
                self.native_max_value,
            )

            if int_value < -32768 or int_value > 32767:
                raise HomeAssistantError(
                    f"Requested value {value} is outside the supported int16 range for register {self._address}"
                )

            if value < self.native_min_value or value > self.native_max_value:
                raise HomeAssistantError(
                    f"Requested value {value} is outside the safe range {self.native_min_value}..{self.native_max_value}"
                )

            success = await self._coordinator.hass.async_add_executor_job(
                self._coordinator.modbus_client.write_register, self._address, int_value
            )
            if success:
                _LOGGER.info("Set register %d to %d", self._address, int_value)
                # Update the locally cached value immediately and let the next
                # regular coordinator poll reconcile device state. This avoids
                # hammering the Modbus connection with a full refresh after
                # every rapid control change.
                if self._coordinator.data and self._address in self._coordinator.data:
                    self._coordinator.data[self._address]["value"] = value
                self.async_write_ha_state()
            else:
                detail = self._coordinator.modbus_client.last_write_error
                if detail:
                    raise HomeAssistantError(f"Failed to set register {self._address}: {detail}")
                raise HomeAssistantError(f"Failed to set register {self._address}")
        except HomeAssistantError:
            raise
        except Exception as err:
            _LOGGER.exception("Error setting register value: %s", err)
            raise HomeAssistantError(f"Error setting register {self._address}: {err}") from err

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
