"""Test APstorage integration register decoding."""
import unittest
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


if __name__ == "__main__":
    unittest.main()
