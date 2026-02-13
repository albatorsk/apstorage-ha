"""Config flow for APstorage integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONNECTION_TCP, CONNECTION_RTU, CONF_CONNECTION_TYPE, CONF_BAUDRATE, CONF_UNIT

_LOGGER = logging.getLogger(__name__)


class APstorageConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle APstorage config flow."""

    VERSION = 1
    
    @staticmethod
    @config_entries.callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return APstorageOptionsFlowHandler(config_entry)
    
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()
            self.data = user_input
            return await self.async_step_select_connection()

        schema = vol.Schema({vol.Required(CONF_HOST): str})
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_select_connection(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select connection type."""
        if user_input is not None:
            self.data.update(user_input)
            if user_input[CONF_CONNECTION_TYPE] == CONNECTION_TCP:
                return await self.async_step_tcp()
            return await self.async_step_rtu()

        schema = vol.Schema(
            {vol.Required(CONF_CONNECTION_TYPE, default=CONNECTION_TCP): vol.In([CONNECTION_TCP, CONNECTION_RTU])}
        )
        return self.async_show_form(step_id="select_connection", data_schema=schema)

    async def async_step_tcp(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure TCP connection."""
        if user_input is not None:
            self.data.update(user_input)
            return await self.async_step_finish()

        schema = vol.Schema(
            {
                vol.Optional(CONF_PORT, default=502): int,
                vol.Optional(CONF_UNIT, default=1): int,
            }
        )
        return self.async_show_form(step_id="tcp", data_schema=schema)

    async def async_step_rtu(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure RTU connection."""
        if user_input is not None:
            self.data.update(user_input)
            return await self.async_step_finish()

        schema = vol.Schema(
            {
                vol.Optional(CONF_BAUDRATE, default=9600): vol.In(
                    [300, 600, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]
                ),
                vol.Optional(CONF_UNIT, default=1): int,
            }
        )
        return self.async_show_form(step_id="rtu", data_schema=schema)

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure scan interval."""
        if user_input is not None:
            self.data.update(user_input)
            return self.async_create_entry(title=self.data[CONF_HOST], data=self.data)

        schema = vol.Schema({vol.Optional("scan_interval", default=30): int})
        return self.async_show_form(step_id="finish", data_schema=schema)


# Register the config flow
APstorageConfigFlow.DOMAIN = DOMAIN


class APstorageOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle APstorage options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Get current scan_interval from options or use default
        current_scan_interval = self.config_entry.options.get("scan_interval", 30)
        
        schema = vol.Schema(
            {
                vol.Optional(
                    "scan_interval",
                    default=current_scan_interval
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300))
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
