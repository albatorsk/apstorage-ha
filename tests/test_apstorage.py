"""Test APstorage integration register decoding."""
import sys
import types
import unittest
from unittest.mock import MagicMock


def _install_homeassistant_stubs() -> None:
    """Install minimal Home Assistant stubs required by the integration module."""
    if "homeassistant" in sys.modules:
        return

    homeassistant = types.ModuleType("homeassistant")
    core = types.ModuleType("homeassistant.core")
    config_entries = types.ModuleType("homeassistant.config_entries")
    const = types.ModuleType("homeassistant.const")
    helpers = types.ModuleType("homeassistant.helpers")
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

    core.HomeAssistant = HomeAssistant
    config_entries.ConfigEntry = ConfigEntry
    const.CONF_HOST = "host"
    const.CONF_PORT = "port"
    const.Platform = Platform
    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator.UpdateFailed = UpdateFailed

    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.const"] = const
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator


_install_homeassistant_stubs()

from custom_components.apstorage import APstorageModbusClient


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
        """Test single register writes use pymodbus 3.11 keyword arguments."""
        response = MagicMock()
        response.isError.return_value = False

        self.client.client = MagicMock()
        self.client.client.write_register.return_value = response

        result = self.client.write_register(40183, 250)

        self.assertTrue(result)
        self.client.client.write_register.assert_called_once_with(
            address=40183,
            value=250,
            device_id=1,
        )


if __name__ == "__main__":
    unittest.main()
