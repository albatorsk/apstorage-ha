"""Config flow for APstorage integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT

from .const import (
    DOMAIN,
    CONNECTION_TCP,
    CONNECTION_RTU,
    CONF_CONNECTION_TYPE,
    CONF_CONNECTION_MAX_AGE_SECONDS,
    CONF_BAUDRATE,
    CONF_UNIT,
    DEFAULT_CONNECTION_MAX_AGE_SECONDS,
    DEFAULT_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class APstorageConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle APstorage config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.data: dict[str, Any] = {}
        self._reconfigure_entry: config_entries.ConfigEntry | None = None
    
    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Get the options flow for this handler."""
        return APstorageOptionsFlowHandler(config_entry)
    
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ):
        """Handle the initial step."""
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()
            self.data = user_input
            return await self.async_step_select_connection()

        schema = vol.Schema({vol.Required(CONF_HOST): str})
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ):
        """Handle reconfiguration from the integration card."""
        if self._reconfigure_entry is None:
            entry_id = self.context.get("entry_id")
            self._reconfigure_entry = self.hass.config_entries.async_get_entry(entry_id)
            if self._reconfigure_entry is None:
                return self.async_abort(reason="unknown")
            self.data = dict(self._reconfigure_entry.data)

        if user_input is not None:
            self.data.update(user_input)
            return await self.async_step_select_connection()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST,
                    default=self._reconfigure_entry.data.get(CONF_HOST, ""),
                ): str
            }
        )
        return self.async_show_form(step_id="reconfigure", data_schema=schema)

    async def async_step_select_connection(
        self, user_input: dict[str, Any] | None = None
    ):
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
    ):
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
    ):
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
    ):
        """Configure scan interval."""
        if user_input is not None:
            self.data.update(user_input)

            # Reconfiguration updates the existing config entry instead of creating a new one.
            if self._reconfigure_entry is not None:
                self.hass.config_entries.async_update_entry(
                    self._reconfigure_entry,
                    data=self.data,
                )
                await self.hass.config_entries.async_reload(self._reconfigure_entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")

            return self.async_create_entry(title=self.data[CONF_HOST], data=self.data)

        schema = vol.Schema(
            {
                vol.Optional(
                    "scan_interval", default=int(DEFAULT_SCAN_INTERVAL.total_seconds())
                ): int
            }
        )
        return self.async_show_form(step_id="finish", data_schema=schema)


# Register the config flow
APstorageConfigFlow.DOMAIN = DOMAIN


class APstorageOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle APstorage options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ):
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Get current scan_interval from options or use default
        current_scan_interval = self._config_entry.options.get(
            "scan_interval", int(DEFAULT_SCAN_INTERVAL.total_seconds())
        )
        current_connection_max_age = self._config_entry.options.get(
            CONF_CONNECTION_MAX_AGE_SECONDS,
            self._config_entry.data.get(
                CONF_CONNECTION_MAX_AGE_SECONDS,
                DEFAULT_CONNECTION_MAX_AGE_SECONDS,
            ),
        )
        
        schema = vol.Schema(
            {
                vol.Optional(
                    "scan_interval",
                    default=current_scan_interval
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                vol.Optional(
                    CONF_CONNECTION_MAX_AGE_SECONDS,
                    default=current_connection_max_age,
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=86400)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
