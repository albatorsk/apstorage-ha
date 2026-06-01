"""Shared entity helpers for the APstorage integration."""
from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


class APstorageEntityMixin:
    """Shared logic for APstorage entities."""

    _coordinator: Any
    _entry: Any

    @staticmethod
    def _model_from_serial(serial_number: str | None) -> str | None:
        """Map known serial prefixes to user-friendly APstorage model names."""
        if not isinstance(serial_number, str):
            return None
        if serial_number.startswith("B050"):
            return "ELT-12"
        if serial_number.startswith("B040"):
            return "ELS-11.4"
        if serial_number.startswith("215"):
            return "ELT-5K"
        return None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the APstorage device."""
        manufacturer = "APstorage"
        model = "Battery Management System"
        serial_number = None
        sw_version = None

        if self._coordinator.data:
            if 40004 in self._coordinator.data:
                mfr = self._coordinator.data[40004].get("value")
                if isinstance(mfr, str) and mfr.strip():
                    manufacturer = mfr

            if 40020 in self._coordinator.data:
                mdl = self._coordinator.data[40020].get("value")
                if isinstance(mdl, str) and mdl.strip():
                    model = mdl

            if 40052 in self._coordinator.data:
                sn = self._coordinator.data[40052].get("value")
                if isinstance(sn, str) and sn.strip():
                    serial_number = sn

            mapped_model = self._model_from_serial(serial_number)
            if mapped_model:
                model = mapped_model

            if 40044 in self._coordinator.data:
                ver = self._coordinator.data[40044].get("value")
                if isinstance(ver, str) and ver.strip():
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