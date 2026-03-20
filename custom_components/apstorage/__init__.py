"""APstorage integration: setup and coordinator."""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    APSTORAGE_REGISTERS,
    APSTORAGE_SCALE_REGISTERS,
    CHARGE_STATUS_ENUM,
    CONF_BAUDRATE,
    CONF_CONNECTION_MAX_AGE_SECONDS,
    CONF_CONNECTION_TYPE,
    CONNECTION_TCP,
    CONNECTION_RTU,
    DEFAULT_CONNECTION_MAX_AGE_SECONDS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.NUMBER, Platform.BINARY_SENSOR]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up APstorage from YAML config."""
    hass.data.setdefault(DOMAIN, {})
    _LOGGER.debug("APstorage integration initialized")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up APstorage from ConfigEntry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}

    scan_interval_seconds = entry.options.get(
        "scan_interval", entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL.total_seconds())
    )
    connection_max_age_seconds = entry.options.get(
        CONF_CONNECTION_MAX_AGE_SECONDS,
        entry.data.get(CONF_CONNECTION_MAX_AGE_SECONDS, DEFAULT_CONNECTION_MAX_AGE_SECONDS),
    )

    # Create coordinator
    coordinator = APstorageCoordinator(
        hass,
        host=entry.data.get(CONF_HOST),
        port=entry.data.get(CONF_PORT, 502),
        unit=entry.data.get("unit", 1),
        connection_type=entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TCP),
        scan_interval=timedelta(seconds=scan_interval_seconds),
        baudrate=int(entry.data.get(CONF_BAUDRATE, 9600)),
        connection_max_age_seconds=connection_max_age_seconds,
    )

    if not await coordinator.async_init():
        _LOGGER.error("Failed to initialize APstorage coordinator")
        return False

    # Don't block setup on initial connection; allow it to fail and retry in background.
    # This prevents Home Assistant from becoming unresponsive if the device is unreachable.
    try:
        connected = await asyncio.wait_for(
            coordinator.async_init(),
            timeout=10.0
        )
        if not connected:
            _LOGGER.warning(
                "Failed to connect to APstorage device at %s:%s during setup; will retry in background",
                entry.data.get(CONF_HOST),
                entry.data.get(CONF_PORT, 502),
            )
    except asyncio.TimeoutError:
        _LOGGER.warning(
            "Connection to APstorage device at %s:%s timed out during setup (10s); will retry in background",
            entry.data.get(CONF_HOST),
            entry.data.get(CONF_PORT, 502),
        )
    except Exception as err:  # pragma: no cover
        _LOGGER.warning(
            "Error during APstorage setup connection: %s; will retry in background",
            err,
        )

    await coordinator.async_refresh()
    if not coordinator.last_update_success:
        _LOGGER.debug(
            "Initial APstorage refresh failed during setup; entities may be created without data until a later refresh succeeds"
        )

    hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator

    # Forward platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a ConfigEntry."""
    coordinator: APstorageCoordinator | None = hass.data[DOMAIN].get(entry.entry_id, {}).get("coordinator")
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        if coordinator is not None:
            await coordinator.async_shutdown()
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


class APstorageModbusClient:
    """Wrapper for pymodbus TCP/RTU client."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        unit: int,
        connection_type: str,
        baudrate: int = 9600,
        connection_max_age_seconds: int = DEFAULT_CONNECTION_MAX_AGE_SECONDS,
    ):
        self.hass = hass
        self.host = host
        self.port = port
        self.unit = unit
        self.connection_type = connection_type
        self.baudrate = baudrate
        self.connection_max_age_seconds = max(0, int(connection_max_age_seconds))
        self.client = None
        self._client_lock = threading.Lock()
        self._last_connect_monotonic: float | None = None

    def _create_client(self):
        """Create a new pymodbus client instance."""
        from pymodbus.client import ModbusTcpClient, ModbusSerialClient

        if self.connection_type == CONNECTION_TCP:
            return ModbusTcpClient(self.host, port=self.port)

        return ModbusSerialClient(
            port=self.host,
            baudrate=self.baudrate,
            stopbits=1,
            bytesize=8,
            parity="N",
            timeout=3,
        )

    def _is_client_connected(self) -> bool:
        """Best-effort check if the underlying client connection is still alive."""
        if self.client is None:
            return False

        connected = getattr(self.client, "connected", None)
        if isinstance(connected, bool):
            return connected

        is_socket_open = getattr(self.client, "is_socket_open", None)
        if callable(is_socket_open):
            try:
                return bool(is_socket_open())
            except Exception:
                return False

        # Fall back to assuming connected when no explicit API is available.
        return True

    def _sync_disconnect(self) -> None:
        """Close the current client connection synchronously."""
        with self._client_lock:
            if self.client is not None:
                try:
                    self.client.close()
                except Exception as err:  # pragma: no cover
                    _LOGGER.debug("Error closing Modbus client: %s", err)
            self.client = None
            self._last_connect_monotonic = None

    def _sync_connect(self, force_reconnect: bool = False) -> bool:
        """Connect (or reconnect) to the Modbus device synchronously."""
        with self._client_lock:
            if not force_reconnect and self._is_client_connected():
                return True

            if self.client is not None:
                try:
                    self.client.close()
                except Exception as err:  # pragma: no cover
                    _LOGGER.debug("Error closing existing Modbus client before reconnect: %s", err)

            self.client = self._create_client()
            connected = bool(self.client.connect())
            if not connected:
                _LOGGER.error("Failed to connect to Modbus device at %s:%s", self.host, self.port)
                self.client = None
                self._last_connect_monotonic = None
                return False

            self._last_connect_monotonic = time.monotonic()
            _LOGGER.info("Connected to APstorage Modbus device")
            return True

    def _should_recycle_connection(self) -> bool:
        """Return True if the connection should be recycled due to age."""
        if self.connection_type != CONNECTION_TCP:
            return False
        if self.connection_max_age_seconds <= 0:
            return False
        if self._last_connect_monotonic is None:
            return False
        return (time.monotonic() - self._last_connect_monotonic) >= self.connection_max_age_seconds

    def _ensure_connected(self, recycle_if_old: bool = False) -> bool:
        """Ensure there is an active connection; optionally recycle old connections."""
        if recycle_if_old and self._should_recycle_connection():
            _LOGGER.debug(
                "Recycling APstorage Modbus TCP connection after %.0f seconds",
                time.monotonic() - self._last_connect_monotonic,
            )
            return self._sync_connect(force_reconnect=True)

        return self._sync_connect(force_reconnect=False)

    async def async_connect(self):
        """Connect to the Modbus device."""
        try:
            return await asyncio.wait_for(
                self.hass.async_add_executor_job(self._sync_connect),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            _LOGGER.error(
                "Connection to Modbus device at %s:%s timed out after 10 seconds",
                self.host,
                self.port,
            )
            return False
        except Exception as err:  # pragma: no cover
            _LOGGER.exception("Failed to init Modbus client: %s", err)
            return False

    async def async_disconnect(self) -> None:
        """Disconnect from the Modbus device."""
        await self.hass.async_add_executor_job(self._sync_disconnect)

    def read_registers(self, address: int, count: int) -> list[int] | None:
        """Read holding registers synchronously."""
        try:
            if not self._ensure_connected(recycle_if_old=True):
                _LOGGER.debug(
                    "Skipping Modbus read for %s:%s address=%d count=%d device_id=%d because client is not connected",
                    self.host,
                    self.port,
                    address,
                    count,
                    self.unit,
                )
                return None
            rr = self.client.read_holding_registers(
                address=address,
                count=count,
                device_id=self.unit,
            )
            if rr.isError():
                _LOGGER.warning(
                    "Modbus read failed for %s:%s address=%d count=%d device_id=%d: %s",
                    self.host,
                    self.port,
                    address,
                    count,
                    self.unit,
                    rr,
                )
                if self._sync_connect(force_reconnect=True):
                    retry = self.client.read_holding_registers(
                        address=address,
                        count=count,
                        device_id=self.unit,
                    )
                    if not retry.isError():
                        return retry.registers
                    _LOGGER.warning(
                        "Modbus retry read failed for %s:%s address=%d count=%d device_id=%d: %s",
                        self.host,
                        self.port,
                        address,
                        count,
                        self.unit,
                        retry,
                    )
                return None
            return rr.registers
        except Exception as err:  # pragma: no cover
            _LOGGER.exception(
                "Exception reading Modbus registers for %s:%s address=%d count=%d device_id=%d: %s",
                self.host,
                self.port,
                address,
                count,
                self.unit,
                err,
            )
            try:
                if self._sync_connect(force_reconnect=True):
                    retry = self.client.read_holding_registers(
                        address=address,
                        count=count,
                        device_id=self.unit,
                    )
                    if not retry.isError():
                        return retry.registers
            except Exception as retry_err:  # pragma: no cover
                _LOGGER.debug("Retry read after reconnect failed: %s", retry_err)
            return None

    def write_register(self, address: int, value: int) -> bool:
        """Write a single holding register synchronously."""
        try:
            if not self._ensure_connected(recycle_if_old=True):
                return False
            # Modbus registers are 16-bit values on the wire. For signed int16
            # semantics, encode negatives as two's-complement before sending.
            write_value = value & 0xFFFF if value < 0 else value
            result = self.client.write_register(
                address=address,
                value=write_value,
                device_id=self.unit,
            )
            if result.isError():
                _LOGGER.warning("Modbus error writing register %d: %s", address, result)
                if self._sync_connect(force_reconnect=True):
                    retry = self.client.write_register(
                        address=address,
                        value=write_value,
                        device_id=self.unit,
                    )
                    if not retry.isError():
                        _LOGGER.debug("Write register %d succeeded after reconnect", address)
                        return True
                    _LOGGER.warning("Modbus retry write error on register %d: %s", address, retry)
                return False
            _LOGGER.debug("Successfully wrote value %d to register %d", value, address)
            return True
        except Exception as err:  # pragma: no cover
            _LOGGER.exception("Exception writing register: %s", err)
            try:
                if self._sync_connect(force_reconnect=True):
                    retry = self.client.write_register(
                        address=address,
                        value=value,
                        device_id=self.unit,
                    )
                    if not retry.isError():
                        _LOGGER.debug("Write register %d succeeded after reconnect", address)
                        return True
            except Exception as retry_err:  # pragma: no cover
                _LOGGER.debug("Retry write after reconnect failed: %s", retry_err)
            return False

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
            elif value_type == "bitfield32":
                # combine two 16-bit registers big-endian for bitfield
                val = (registers[0] << 16) | registers[1]
                return val  # Return raw bitfield value
            elif value_type == "enum16":
                val = CHARGE_STATUS_ENUM.get(registers[0], f"UNKNOWN({registers[0]})")
                return val
            elif value_type == "string":
                # Decode string from registers (2 bytes per register, ASCII)
                chars = []
                for reg in registers:
                    # Each register contains 2 bytes (big-endian)
                    chars.append(chr((reg >> 8) & 0xFF))
                    chars.append(chr(reg & 0xFF))
                # Strip null bytes and whitespace
                return ''.join(chars).replace('\x00', '').strip()
            elif value_type == "sunssf":
                # SunSpec scale factor (signed 16-bit)
                val = registers[0]
                if val > 32767:
                    val = val - 65536
                return val  # Return raw scale factor
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
        connection_max_age_seconds: int = DEFAULT_CONNECTION_MAX_AGE_SECONDS,
    ):
        self.modbus_client = APstorageModbusClient(
            hass,
            host,
            port,
            unit,
            connection_type,
            baudrate,
            connection_max_age_seconds,
        )
        
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

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator and close Modbus resources."""
        await self.modbus_client.async_disconnect()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the device."""
        try:
            data = {}
            # Read all scale factor registers first
            scale_factors = {}
            for value_reg, scale_reg in APSTORAGE_SCALE_REGISTERS.items():
                scale_regs = await self.hass.async_add_executor_job(
                    self.modbus_client.read_registers, scale_reg, 1
                )
                if scale_regs is not None:
                    # Signed 16-bit for scale factor
                    sf = scale_regs[0]
                    if sf > 32767:
                        sf = sf - 65536
                    scale_factors[value_reg] = sf
                else:
                    _LOGGER.debug(
                        "Scale factor register %d could not be read for value register %d",
                        scale_reg,
                        value_reg,
                    )

            # Read all configured registers
            for address, (name, count, value_type, scale, unit, _) in APSTORAGE_REGISTERS.items():
                registers = await self.hass.async_add_executor_job(
                    self.modbus_client.read_registers, address, count
                )
                if registers is not None:
                    # Use dynamic scale factor if available
                    if address in scale_factors:
                        sf = scale_factors[address]
                        decoded = self.modbus_client.decode_register(registers, value_type, 1)
                        value = decoded * (10 ** sf)
                    else:
                        value = self.modbus_client.decode_register(registers, value_type, scale)
                    data[address] = {
                        "name": name,
                        "value": value,
                        "unit": unit,
                        "type": value_type,
                    }
                else:
                    _LOGGER.debug("Register read returned no data for %s (%d)", name, address)

            if not data:
                raise UpdateFailed(
                    "No APstorage registers could be read; enable debug logging for custom_components.apstorage to inspect Modbus failures"
                )

            return data
        except Exception as err:  # pragma: no cover
            raise UpdateFailed(err) from err

