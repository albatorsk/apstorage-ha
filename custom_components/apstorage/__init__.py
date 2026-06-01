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
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    APSTORAGE_REGISTERS,
    APSTORAGE_SCALE_REGISTERS,
    CHARGE_STATUS_ENUM,
    CONF_BAUDRATE,
    CONF_CONNECTION_MAX_AGE_SECONDS,
    CONF_CONNECTION_TYPE,
    CONF_REGISTER_ADDRESS_OFFSET,
    CONNECTION_TCP,
    CONNECTION_RTU,
    DEFAULT_CONNECTION_MAX_AGE_SECONDS,
    DEFAULT_REGISTER_ADDRESS_OFFSET,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER_NAME,
)

_LOGGER = logging.getLogger(LOGGER_NAME)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
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
    register_address_offset = int(
        entry.options.get(
            CONF_REGISTER_ADDRESS_OFFSET,
            entry.data.get(CONF_REGISTER_ADDRESS_OFFSET, DEFAULT_REGISTER_ADDRESS_OFFSET),
        )
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
        register_address_offset=register_address_offset,
    )

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

    _READ_AFTER_WRITE_DELAY_SECONDS = 1.5

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        unit: int,
        connection_type: str,
        baudrate: int = 9600,
        connection_max_age_seconds: int = DEFAULT_CONNECTION_MAX_AGE_SECONDS,
        register_address_offset: int = DEFAULT_REGISTER_ADDRESS_OFFSET,
    ):
        self.hass = hass
        self.host = host
        self.port = port
        self.unit = unit
        self.connection_type = connection_type
        self.baudrate = baudrate
        self.connection_max_age_seconds = max(0, int(connection_max_age_seconds))
        self.register_address_offset = int(register_address_offset)
        self.client = None
        self.last_write_error: str | None = None
        self._client_lock = threading.Lock()
        self._request_lock = threading.Lock()
        self._last_connect_monotonic: float | None = None
        self._last_successful_write_monotonic: float | None = None

    def _to_wire_address(self, address: int) -> int:
        """Convert logical register address to Modbus wire address."""
        return int(address) + self.register_address_offset

    def should_defer_reads(self) -> bool:
        """Return True when reads should wait briefly after a successful write."""
        if self._last_successful_write_monotonic is None:
            return False
        return (
            time.monotonic() - self._last_successful_write_monotonic
        ) < self._READ_AFTER_WRITE_DELAY_SECONDS

    # Hard ceiling on how long any single Modbus TCP operation may take.
    # Without this, a firewall that silently drops packets can stall an
    # executor thread forever, eventually exhausting HA's thread pool and
    # freezing the entire UI.
    _MODBUS_SOCKET_TIMEOUT_SECONDS = 5

    def _create_client(self):
        """Create a new pymodbus client instance."""
        from pymodbus.client import ModbusTcpClient, ModbusSerialClient

        if self.connection_type == CONNECTION_TCP:
            return ModbusTcpClient(
                self.host,
                port=self.port,
                timeout=self._MODBUS_SOCKET_TIMEOUT_SECONDS,
            )

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
            wire_address = self._to_wire_address(address)
            with self._request_lock:
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
                    address=wire_address,
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
                            address=wire_address,
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
                        address=wire_address,
                        count=count,
                        device_id=self.unit,
                    )
                    if not retry.isError():
                        return retry.registers
            except Exception as retry_err:  # pragma: no cover
                _LOGGER.debug("Retry read after reconnect failed: %s", retry_err)
            return None

    def write_register(self, address: int, value: int) -> bool:
        """Write a single holding register synchronously.

        Tries both Modbus function 16 (write multiple) and function 6 (write
        single), as device behavior can vary by firmware.
        """
        try:
            self.last_write_error = None
            wire_address = self._to_wire_address(address)
            attempt_errors: list[str] = []
            if not -32768 <= value <= 32767:
                _LOGGER.error(
                    "Refusing to write out-of-range int16 value %d to register %d",
                    value,
                    address,
                )
                self.last_write_error = (
                    f"Refusing out-of-range int16 value {value} for register {address}"
                )
                return False

            # Modbus registers are 16-bit values on the wire. For signed int16
            # semantics, encode negatives as two's-complement before sending.
            write_value = value & 0xFFFF if value < 0 else value

            def _attempt_write(method: str):
                if method == "write_registers":
                    writer = getattr(self.client, "write_registers", None)
                    if not callable(writer):
                        return None
                    return writer(
                        address=wire_address,
                        values=[write_value],
                        device_id=self.unit,
                    )

                return self.client.write_register(
                    address=wire_address,
                    value=write_value,
                    device_id=self.unit,
                )

            method_order = ["write_registers", "write_register"]
            if not callable(getattr(self.client, "write_registers", None)):
                method_order = ["write_register"]

            with self._request_lock:
                if not self._ensure_connected(recycle_if_old=True):
                    self.last_write_error = "Modbus client is not connected"
                    return False

                for reconnect in (False, True):
                    if reconnect and not self._sync_connect(force_reconnect=True):
                        continue

                    for method in method_order:
                        try:
                            result = _attempt_write(method)
                        except Exception as err:  # pragma: no cover
                            self.last_write_error = (
                                f"{method} exception for register {address} (wire={wire_address}): {err}"
                            )
                            attempt_errors.append(self.last_write_error)
                            _LOGGER.debug(self.last_write_error)
                            continue

                        if result is None:
                            continue

                        if not result.isError():
                            _LOGGER.debug(
                                "Successfully wrote value %d to register %d (wire=%d) using %s after %d transient errors",
                                value,
                                address,
                                wire_address,
                                method,
                                len(attempt_errors),
                            )
                            self._last_successful_write_monotonic = time.monotonic()
                            self.last_write_error = None
                            return True

                        self.last_write_error = (
                            f"{method} failed for register {address} (wire={wire_address}): {result}"
                        )
                        attempt_errors.append(self.last_write_error)
                        _LOGGER.debug(self.last_write_error)

            if self.last_write_error is None:
                self.last_write_error = (
                    f"Unknown Modbus write failure for register {address} (wire={wire_address})"
                )
            if attempt_errors:
                _LOGGER.warning(
                    "Write failed for register %d (wire=%d) after %d attempts; last error: %s",
                    address,
                    wire_address,
                    len(attempt_errors),
                    self.last_write_error,
                )
            _LOGGER.error(self.last_write_error)
            return False
        except Exception as err:  # pragma: no cover
            _LOGGER.exception("Exception writing register: %s", err)
            self.last_write_error = f"Exception writing register {address}: {err}"
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

    _MAX_MODBUS_BATCH_READ_COUNT = 125

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
        register_address_offset: int = DEFAULT_REGISTER_ADDRESS_OFFSET,
    ):
        self.modbus_client = APstorageModbusClient(
            hass,
            host,
            port,
            unit,
            connection_type,
            baudrate,
            connection_max_age_seconds,
            register_address_offset,
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

    @classmethod
    def _build_read_batches(cls) -> list[tuple[int, int]]:
        """Build contiguous Modbus read batches from configured register spans."""
        batches: list[tuple[int, int]] = []
        spans = sorted(
            (address, address + count - 1)
            for address, (_, count, _, _, _, _) in APSTORAGE_REGISTERS.items()
        )
        if not spans:
            return batches

        batch_start, batch_end = spans[0]
        for span_start, span_end in spans[1:]:
            proposed_end = max(batch_end, span_end)
            proposed_count = proposed_end - batch_start + 1

            if span_start <= batch_end + 1 and proposed_count <= cls._MAX_MODBUS_BATCH_READ_COUNT:
                batch_end = proposed_end
                continue

            batches.append((batch_start, batch_end))
            batch_start, batch_end = span_start, span_end

        batches.append((batch_start, batch_end))
        return batches

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the device."""
        # Overall guard: if this update takes longer than this many seconds,
        # cancel it rather than letting stuck executor threads pile up.
        _UPDATE_TIMEOUT_SECONDS = 30
        try:
            return await asyncio.wait_for(
                self._async_fetch_data(),
                timeout=_UPDATE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as err:
            raise UpdateFailed(
                f"APstorage data update timed out after {_UPDATE_TIMEOUT_SECONDS}s; "
                "check device reachability"
            ) from err
        except Exception as err:  # pragma: no cover
            raise UpdateFailed(err) from err

    async def _async_fetch_data(self) -> dict[str, Any]:
        """Inner fetch implementation called by _async_update_data."""
        if self.modbus_client.should_defer_reads() and getattr(self, "data", None):
            _LOGGER.debug(
                "Skipping APstorage poll because a successful write occurred within the last %.1f seconds",
                self.modbus_client._READ_AFTER_WRITE_DELAY_SECONDS,
            )
            return self.data

        data = {}
        raw_by_address: dict[int, list[int]] = {}

        # Read configured registers in contiguous batches to reduce Modbus requests.
        for batch_start, batch_end in self._build_read_batches():
            count = batch_end - batch_start + 1
            batch_registers = await self.hass.async_add_executor_job(
                self.modbus_client.read_registers, batch_start, count
            )
            if batch_registers is None:
                _LOGGER.debug(
                    "Batch register read returned no data for start=%d end=%d count=%d",
                    batch_start,
                    batch_end,
                    count,
                )
                continue

            for address, (_, reg_count, _, _, _, _) in APSTORAGE_REGISTERS.items():
                if address < batch_start:
                    continue
                reg_end = address + reg_count - 1
                if reg_end > batch_end:
                    continue
                if address in raw_by_address:
                    continue

                offset = address - batch_start
                registers = batch_registers[offset : offset + reg_count]
                if len(registers) == reg_count:
                    raw_by_address[address] = registers

        # Resolve scale factors from previously read register data.
        scale_factors = {}
        for value_reg, scale_reg in APSTORAGE_SCALE_REGISTERS.items():
            scale_regs = raw_by_address.get(scale_reg)
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

        # Decode all configured registers from raw values.
        for address, (name, count, value_type, scale, unit, _) in APSTORAGE_REGISTERS.items():
            registers = raw_by_address.get(address)
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
                "No APstorage registers could be read; enable debug logging for custom_components.apstorage_ha to inspect Modbus failures"
            )

        return data

