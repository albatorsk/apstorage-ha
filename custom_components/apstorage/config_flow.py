"""Config flow for APstorage integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_UNIT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONNECTION_TCP, CONNECTION_RTU, CONF_CONNECTION_TYPE, CONF_BAUDRATE

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
    }
)


async def async_validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate user input (minimal validation)."""
    # Just ensure host is provided; connection validation happens during setup
    if not data.get(CONF_HOST):
        return {"base": "invalid_host"}
    
    return {"title": f"APstorage {data.get(CONF_HOST)}"}


class APstorageConfigFlow(config_entries.ConfigFlow):
    """Handle APstorage config flow."""

    VERSION = 1
    DOMAIN = DOMAIN

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Check if entry already exists
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()

            # Validate input
            validation_result = await async_validate_input(self.hass, user_input)
            if "base" in validation_result:
                errors["base"] = validation_result["base"]
            else:
                # Store data and proceed to next step
                self.flow_config = user_input.copy()
                return await self.async_step_connection_type()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={},
        )

    async def async_step_connection_type(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle connection type selection."""
        errors = {}

        if user_input is not None:
            self.flow_config.update(user_input)
            if user_input.get(CONF_CONNECTION_TYPE) == CONNECTION_TCP:
                return await self.async_step_tcp_config()
            else:
                return await self.async_step_rtu_config()

        schema = vol.Schema(
            {
                vol.Required(CONF_CONNECTION_TYPE, default=CONNECTION_TCP): vol.In(
                    [CONNECTION_TCP, CONNECTION_RTU]
                ),
            }
        )

        return self.async_show_form(
            step_id="connection_type",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_tcp_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle TCP configuration."""
        errors = {}

        if user_input is not None:
            self.flow_config.update(user_input)
            return await self.async_step_device_config()

        schema = vol.Schema(
            {
                vol.Optional(CONF_PORT, default=502): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
                vol.Optional(CONF_UNIT, default=1): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=247)
                ),
            }
        )

        return self.async_show_form(
            step_id="tcp_config",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_rtu_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle RTU configuration."""
        errors = {}

        if user_input is not None:
            self.flow_config.update(user_input)
            return await self.async_step_device_config()

        schema = vol.Schema(
            {
                vol.Optional(CONF_BAUDRATE, default=9600): vol.In(
                    [300, 600, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]
                ),
                vol.Optional(CONF_UNIT, default=1): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=247)
                ),
            }
        )

        return self.async_show_form(
            step_id="rtu_config",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_device_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle device configuration (scan interval)."""
        errors = {}

        if user_input is not None:
            self.flow_config.update(user_input)
            # Create the config entry
            return self.async_create_entry(
                title=self.flow_config.get(CONF_HOST),
                data=self.flow_config,
            )

        schema = vol.Schema(
            {
                vol.Optional("scan_interval", default=30): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=300)
                ),
            }
        )

        return self.async_show_form(
            step_id="device_config",
            data_schema=schema,
            errors=errors,
        )
