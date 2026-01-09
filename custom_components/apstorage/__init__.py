"""APstorage integration: setup and coordinator."""
from __future__ import annotations

import logging
from typing import Any
import struct

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL, CONNECTION_TCP, CONNECTION_RTU, APSTORAGE_REGISTERS, CHARGE_STATUS_ENUM, CONF_CONNECTION_TYPE, CONF_BAUDRATE

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up APstorage from YAML config."""
    hass.data.setdefault(DOMAIN, {})
    _LOGGER.debug("APstorage integration initialized")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up APstorage from ConfigEntry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}

    # Create coordinator
    coordinator = APstorageCoordinator(
        hass,
        host=entry.data.get(CONF_HOST),
        port=entry.data.get(CONF_PORT, 502),
        unit=entry.data.get("unit", 1),
        connection_type=entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TCP),
        scan_interval=None,  # will use default
        baudrate=entry.data.get(CONF_BAUDRATE, 9600),
    )

    if not await coordinator.async_init():
        _LOGGER.error("Failed to initialize APstorage coordinator")
        return False

    hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator

    # Forward platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a ConfigEntry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


class APstorageModbusClient:
    """Wrapper for pymodbus TCP/RTU client."""

    def __init__(self, hass: HomeAssistant, host: str, port: int, unit: int, 
                 connection_type: str, baudrate: int = 9600):
        self.hass = hass
        self.host = host
        self.port = port
        self.unit = unit
        self.connection_type = connection_type
        self.baudrate = baudrate
        self.client = None

    async def async_connect(self):
        """Connect to the Modbus device."""
        try:
            from pymodbus.client.sync import ModbusTcpClient, ModbusSerialClient

            if self.connection_type == CONNECTION_TCP:
                self.client = ModbusTcpClient(self.host, port=self.port)
            else:  # RTU
                self.client = ModbusSerialClient(
                    method="rtu",
                    port=self.host,
                    baudrate=self.baudrate,
                    stopbits=1,
                    bytesize=8,
                    parity="N",
                    timeout=3,
                )
            if not self.client.connect():
                _LOGGER.error("Failed to connect to Modbus device at %s:%s", self.host, self.port)
                return False
            _LOGGER.info("Connected to APstorage Modbus device")
            return True
        except Exception as err:  # pragma: no cover
            _LOGGER.exception("Failed to init Modbus client: %s", err)
            return False

    def read_registers(self, address: int, count: int) -> list[int] | None:
        """Read holding registers synchronously."""
        try:
            if not self.client:
                return None
            rr = self.client.read_holding_registers(address, count, unit=self.unit)
            if rr.isError():
                _LOGGER.warning("Modbus error reading registers %d+%d: %s", address, count, rr)
                return None
            return rr.registers
        except Exception as err:  # pragma: no cover
            _LOGGER.exception("Exception reading registers: %s", err)
            return None

    def decode_register(self, registers: list[int], value_type: str, scale: float):
        """Decode register(s) based on type and scale."""
        if not registers:
            return None
        try:
            if value_type == "uint16":
                val = registers[0]
            elif value_type == "int16":
                # signed 16-bit
                val = registers[0]
                if val > 32767:
                    val = val - 65536
            elif value_type == "uint32":
                # combine two 16-bit registers big-endian
                val = (registers[0] << 16) | registers[1]
            elif value_type == "enum16":
                val = CHARGE_STATUS_ENUM.get(registers[0], f"UNKNOWN({registers[0]})")
                return val
            else:
                return None

            # Apply scale
            return val * scale
        except Exception as err:  # pragma: no cover
            _LOGGER.exception("Error decoding register: %s", err)
            return None


class APstorageCoordinator(DataUpdateCoordinator):
    """Coordinator to poll APstorage device."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        unit: int,
        connection_type: str,
        scan_interval=None,
        baudrate: int = 9600,
    ):
        self.modbus_client = APstorageModbusClient(hass, host, port, unit, connection_type, baudrate)
        
        if scan_interval is None:
            scan_interval = DEFAULT_SCAN_INTERVAL

        super().__init__(
            hass,
            _LOGGER,
            name="APstorage Modbus",
            update_method=self._async_update_data,
            update_interval=scan_interval,
        )

    async def async_init(self) -> bool:
        """Initialize the coordinator."""
        return await self.modbus_client.async_connect()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the device."""
        try:
            data = {}
            # Read all configured registers
            for address, (name, count, value_type, scale, unit, _) in APSTORAGE_REGISTERS.items():
                registers = await self.hass.async_add_executor_job(
                    self.modbus_client.read_registers, address, count
                )
                if registers is not None:
                    decoded = self.modbus_client.decode_register(registers, value_type, scale)
                    data[address] = {
                        "name": name,
                        "value": decoded,
                        "unit": unit,
                        "type": value_type,
                    }
            return data
        except Exception as err:  # pragma: no cover
            raise UpdateFailed(err) from err

