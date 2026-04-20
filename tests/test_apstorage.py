"""Test APstorage integration register decoding."""
import sys
import time
import types
import unittest
from unittest.mock import MagicMock, call


def _install_homeassistant_stubs() -> None:
    """Install minimal Home Assistant stubs required by the integration module."""
    if "homeassistant" in sys.modules:
        return

    homeassistant = types.ModuleType("homeassistant")
    core = types.ModuleType("homeassistant.core")
    config_entries = types.ModuleType("homeassistant.config_entries")
    const = types.ModuleType("homeassistant.const")
    helpers = types.ModuleType("homeassistant.helpers")
    entity_registry = types.ModuleType("homeassistant.helpers.entity_registry")
    config_validation = types.ModuleType("homeassistant.helpers.config_validation")
    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")

    class HomeAssistant:  # noqa: D401
        """Stub HomeAssistant class."""

    class ConfigEntry:  # noqa: D401
        """Stub ConfigEntry class."""

    class Platform:
        SENSOR = "sensor"
        NUMBER = "number"
        BINARY_SENSOR = "binary_sensor"

    class DataUpdateCoordinator:
        def __init__(self, *args, **kwargs):
            self.hass = args[0] if args else None
            self.last_update_success = True

    class UpdateFailed(Exception):
        """Stub UpdateFailed exception."""

    def async_get(_hass):
        return None

    def config_entry_only_config_schema(_domain):
        return {}

    core.HomeAssistant = HomeAssistant
    config_entries.ConfigEntry = ConfigEntry
    const.CONF_HOST = "host"
    const.CONF_PORT = "port"
    const.Platform = Platform
    entity_registry.async_get = async_get
    config_validation.config_entry_only_config_schema = config_entry_only_config_schema
    helpers.entity_registry = entity_registry
    helpers.config_validation = config_validation
    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator.UpdateFailed = UpdateFailed

    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.const"] = const
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.entity_registry"] = entity_registry
    sys.modules["homeassistant.helpers.config_validation"] = config_validation
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator


_install_homeassistant_stubs()

from custom_components.apstorage import (
    APstorageModbusClient,
    DEFAULT_CONNECTION_MAX_AGE_SECONDS,
)
from custom_components.apstorage.entity_naming import (
    async_migrate_entity_id,
    build_prefixed_entity_id,
    get_suggested_object_id,
)


class TestAPstorageDecoding(unittest.TestCase):
    """Test register decoding logic."""

    def setUp(self):
        """Set up test client."""
        self.client = APstorageModbusClient(
            hass=None, host="test", port=502, unit=1, connection_type="tcp"
        )

    def test_uint16_decode(self):
        """Test uint16 decoding."""
        registers = [1234]
        result = self.client.decode_register(registers, "uint16", 0.1)
        self.assertEqual(result, 123.4)

    def test_int16_decode_positive(self):
        """Test int16 positive value."""
        registers = [1234]
        result = self.client.decode_register(registers, "int16", 1.0)
        self.assertEqual(result, 1234)

    def test_int16_decode_negative(self):
        """Test int16 negative value (two's complement)."""
        registers = [65535]  # -1 in 16-bit two's complement
        result = self.client.decode_register(registers, "int16", 1.0)
        self.assertEqual(result, -1)

    def test_uint32_decode(self):
        """Test uint32 decoding (two 16-bit registers)."""
        registers = [0x0001, 0x0000]
        result = self.client.decode_register(registers, "uint32", 0.01)
        self.assertEqual(result, 65536 * 0.01)

    def test_enum16_decode(self):
        """Test enum16 decoding (charge status)."""
        registers = [4]  # CHARGING
        result = self.client.decode_register(registers, "enum16", 1.0)
        self.assertEqual(result, "CHARGING")

    def test_enum16_unknown(self):
        """Test enum16 with unknown value."""
        registers = [99]  # unknown
        result = self.client.decode_register(registers, "enum16", 1.0)
        self.assertIn("UNKNOWN", result)

    def test_read_registers_uses_pymodbus_311_keywords(self):
        """Test holding register reads use pymodbus 3.11 keyword arguments."""
        response = MagicMock()
        response.isError.return_value = False
        response.registers = [123]

        self.client.client = MagicMock()
        self.client.client.read_holding_registers.return_value = response

        result = self.client.read_registers(40083, 1)

        self.assertEqual(result, [123])
        self.client.client.read_holding_registers.assert_called_once_with(
            address=40083,
            count=1,
            device_id=1,
        )

    def test_write_register_uses_pymodbus_311_keywords(self):
        """Test writes use the safer pymodbus 3.11 multi-register API."""
        response = MagicMock()
        response.isError.return_value = False

        self.client.client = MagicMock()
        self.client.client.write_registers.return_value = response

        result = self.client.write_register(40183, 250)

        self.assertTrue(result)
        self.client.client.write_registers.assert_called_once_with(
            address=40183,
            values=[250],
            device_id=1,
        )

    def test_write_register_encodes_negative_int16_value(self):
        """Test negative register writes are sent as two's-complement uint16."""
        response = MagicMock()
        response.isError.return_value = False

        self.client.client = MagicMock()
        self.client.client.write_registers.return_value = response

        result = self.client.write_register(40183, -1)

        self.assertTrue(result)
        self.client.client.write_registers.assert_called_once_with(
            address=40183,
            values=[65535],
            device_id=1,
        )

    def test_create_client_uses_pymodbus_311_serial_signature(self):
        """Test serial client construction avoids removed method= keyword."""
        serial_client = APstorageModbusClient(
            hass=None,
            host="/dev/ttyUSB0",
            port=502,
            unit=1,
            connection_type="rtu",
            baudrate=9600,
        )

        fake_pymodbus_client = types.ModuleType("pymodbus.client")
        fake_pymodbus_client.ModbusTcpClient = MagicMock()
        fake_pymodbus_client.ModbusSerialClient = MagicMock(return_value="serial-client")

        original_pymodbus_client = sys.modules.get("pymodbus.client")
        sys.modules["pymodbus.client"] = fake_pymodbus_client
        try:
            result = serial_client._create_client()
        finally:
            if original_pymodbus_client is None:
                del sys.modules["pymodbus.client"]
            else:
                sys.modules["pymodbus.client"] = original_pymodbus_client

        self.assertEqual(result, "serial-client")
        fake_pymodbus_client.ModbusSerialClient.assert_called_once_with(
            port="/dev/ttyUSB0",
            baudrate=9600,
            stopbits=1,
            bytesize=8,
            parity="N",
            timeout=3,
        )

    def test_read_registers_reconnects_and_retries_on_error(self):
        """Test failed reads trigger reconnect and one retry."""
        first_response = MagicMock()
        first_response.isError.return_value = True

        retry_response = MagicMock()
        retry_response.isError.return_value = False
        retry_response.registers = [456]

        self.client.client = MagicMock()
        self.client.client.read_holding_registers.side_effect = [first_response, retry_response]
        self.client._sync_connect = MagicMock(return_value=True)

        result = self.client.read_registers(40083, 1)

        self.assertEqual(result, [456])
        self.client._sync_connect.assert_has_calls(
            [call(force_reconnect=False), call(force_reconnect=True)]
        )

    def test_ensure_connected_recycles_old_tcp_connections(self):
        """Test stale TCP sessions are proactively recycled before requests."""
        self.client._last_connect_monotonic = (
            time.monotonic() - DEFAULT_CONNECTION_MAX_AGE_SECONDS - 1
        )
        self.client._sync_connect = MagicMock(return_value=True)

        result = self.client._ensure_connected(recycle_if_old=True)

        self.assertTrue(result)
        self.client._sync_connect.assert_called_once_with(force_reconnect=True)

    def test_suggested_object_id_uses_serial_prefix(self):
        """Test entity object IDs include the aps serial prefix."""
        coordinator_data = {40052: {"value": "SERIAL-42"}}

        result = get_suggested_object_id(coordinator_data, "Charge Status")

        self.assertEqual(result, "aps_serial_42_charge_status")

    def test_build_prefixed_entity_id_preserves_domain(self):
        """Test full entity IDs keep their domain when renamed."""
        coordinator_data = {40052: {"value": "SERIAL-42"}}

        result = build_prefixed_entity_id(
            "sensor.charge_status",
            coordinator_data,
            "Charge Status",
        )

        self.assertEqual(result, "sensor.aps_serial_42_charge_status")

    def test_async_migrate_entity_id_updates_registry(self):
        """Test entity registry entries are renamed to the serial-prefixed ID."""
        coordinator_data = {40052: {"value": "SERIAL-42"}}
        hass = object()

        registry = MagicMock()
        registry.async_get.return_value = object()

        import custom_components.apstorage.entity_naming as entity_naming

        original_async_get = entity_naming.er.async_get
        entity_naming.er.async_get = MagicMock(return_value=registry)
        try:
            result = async_migrate_entity_id(
                hass,
                "sensor.charge_status",
                coordinator_data,
                "Charge Status",
            )
        finally:
            entity_naming.er.async_get = original_async_get

        self.assertTrue(result)
        registry.async_update_entity.assert_called_once_with(
            "sensor.charge_status",
            new_entity_id="sensor.aps_serial_42_charge_status",
        )

    def test_async_migrate_entity_id_does_not_strip_prefix_when_serial_missing(self):
        """Migration must not remove aps_ prefix when coordinator data is absent.

        If coordinator.data is None (e.g. initial refresh failed), calling
        async_migrate_entity_id would previously rename an already-prefixed
        entity back to the bare name, stripping the serial prefix.
        """
        import custom_components.apstorage.entity_naming as entity_naming

        registry = MagicMock()
        hass = object()

        original_async_get = entity_naming.er.async_get
        entity_naming.er.async_get = MagicMock(return_value=registry)
        try:
            # No coordinator data at all
            result_none = async_migrate_entity_id(
                hass,
                "sensor.aps_serial_42_charge_status",
                None,
                "Charge Status",
            )
            # Coordinator data present but serial register missing
            result_no_serial = async_migrate_entity_id(
                hass,
                "sensor.aps_serial_42_charge_status",
                {},
                "Charge Status",
            )
        finally:
            entity_naming.er.async_get = original_async_get

        self.assertFalse(result_none, "Should not migrate when data is None")
        self.assertFalse(result_no_serial, "Should not migrate when serial register is missing")
        registry.async_update_entity.assert_not_called()


if __name__ == "__main__":
    unittest.main()
