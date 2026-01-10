# APstorage Home Assistant Integration

A comprehensive Home Assistant custom integration for APstorage battery systems, supporting Modbus TCP and RTU communication with real-time monitoring and control.

> **⚠️ 100% AI Generated - NOT TESTED - MAY NOT WORK:** This entire integration, including all code, documentation, and configuration, has been generated entirely by AI (GitHub Copilot). **This integration has NOT been tested in a real Home Assistant environment or with actual APstorage devices. It may not work at all.** Use at your own risk and thoroughly test before any production use. Please review all code and validate functionality with your specific hardware.

## Overview

This integration exposes APstorage battery system metrics as Home Assistant sensors, including:
- Battery state (voltage, current, power, SoC, SoH)
- Temperatures (battery and PCS)
- Energy tracking (daily and cumulative)
- 3-phase grid power monitoring
- Device alarms and heartbeat

## Quick Start

### 1. Install Integration

Copy the `custom_components/apstorage` folder to your Home Assistant config directory:

```bash
mkdir -p ~/.homeassistant/custom_components
cp -r custom_components/apstorage ~/.homeassistant/custom_components/
```

### 2. Configure (configuration.yaml)

**Modbus TCP:**
```yaml
apstorage:
  host: 192.168.1.50
  port: 502
  unit: 1
  scan_interval: 30
```

**Modbus RTU (Serial):**
```yaml
apstorage:
  host: /dev/ttyUSB0
  unit: 1
  connection_type: rtu
  baudrate: 9600
  scan_interval: 30
```

### 3. Restart Home Assistant

All APstorage sensors will be created automatically under `sensor.battery_voltage`, `sensor.state_of_charge`, etc.

## Features

✅ **Modbus TCP/RTU Support** – flexible connection types  
✅ **27 Pre-mapped Sensors** – voltage, current, power, temperatures, energy, etc.  
✅ **Real-time Updates** – configurable polling interval (default 30s)  
✅ **Signed/Unsigned Registers** – automatic 16/32-bit decoding  
✅ **Scale Factors** – voltage/current/power properly scaled  
✅ **Status Enumerations** – readable charge status values  

## Supported Sensors

All sensors are created automatically from register mapping:

| Sensor | Address | Unit | Device Class |
|--------|---------|------|--------------|
| Battery Voltage | 40134 | V | voltage |
| DC Current | 40114 | A | current |
| Battery Power | 40117 | W | power |
| State of Charge | 40081 | % | battery |
| State of Health | 40083 | % | - |
| Battery Temperature | 40156 | °C | temperature |
| PCS Temperature | 40157 | °C | temperature |
| Active Power Phases A/B/C | 40135-40137 | W | power |
| Daily Charge/Discharge Energy | 40146-40147 | kWh | energy |
| Grid Power Phases A/B/C | 40153-40155 | W | power |

See [full sensor list](custom_components/apstorage/README.md#exposed-sensors) in integration README.

## Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | string | - | IP address (TCP) or serial port (RTU) |
| `port` | int | 502 | Modbus TCP port |
| `unit` | int | 1 | Modbus unit ID |
| `connection_type` | string | tcp | `tcp` or `rtu` |
| `baudrate` | int | 9600 | Serial baud rate (RTU only) |
| `scan_interval` | int | 30 | Polling interval in seconds |

## Architecture

```
Home Assistant
    └── APstorage Integration (custom_components/apstorage)
        ├── __init__.py          (coordinator, Modbus client)
        ├── sensor.py            (sensor platform)
        ├── const.py             (register definitions, scales)
        ├── manifest.json        (metadata)
        └── strings.json         (i18n, config schema)
```

The integration uses **async-safe Modbus polling** with a coordinator pattern:
- `APstorageModbusClient` – Modbus TCP/RTU communication
- `APstorageCoordinator` – async polling with error handling
- `APstorageRegisterSensor` – Home Assistant sensor entities

## Modbus Register Reference

All registers are from the official [APstorage Modbus documentation](https://per.pe/APstorage-Modbus.pdf).

Example register (Battery Voltage, address 40134):
- **Address:** 40134 (holding register)
- **Type:** uint16 (unsigned 16-bit)
- **Scale:** 0.1 (raw value × 0.1)
- **Unit:** V (volts)
- **Device Class:** voltage

## Scale Factor Calculation

Some registers require applying a scale factor from a separate register.

**Example:**
If SoC = 856 and SoC_SF = -1, then:

    SoC = 856 × 10^-1 = 85.6 (%)

**Another example:**
If SoH = 100 and SoH_SF = 0, then:

    SoH = 100 × 10^0 = 100

## Modbus Query Example

To read SoH (register 0x9C93) from device address 0x01, send:

    0x01 0x03 0x9C 0x93 0x00 0x01 0x5A 0x77

- 0x01: device address
- 0x03: function code
- 0x9C 0x93: starting register address
- 0x00 0x01: number of registers
- 0x5A 0x77: CRC

A response might be:

    0x01 0x03 0x02 0x00 0x64 0xB9 0xAF

- 0x00 0x64: value of register 0x9C93 (100 decimal)
- SoH_SF = 0, so SoH = 100 × 10⁰ = 100

## Troubleshooting

### Connection Refused
```bash
# Test TCP connection
nc -zv 192.168.1.50 502

# Test serial port
ls -la /dev/ttyUSB0
```

### No Sensors Created
- Check Home Assistant logs: `sudo journalctl -u homeassistant`
- Verify Modbus device responds with external client
- Confirm register addresses match APstorage documentation

### RTU Serial Issues
- Linux: `sudo usermod -a -G dialout $USER` (restart required)
- Match device baud rate (usually 9600)
- Verify cable and adapter

## Development

### Run Tests
```bash
python -m pytest tests/test_apstorage.py -v
```

### Add Custom Registers
Edit `custom_components/apstorage/const.py`:
```python
APSTORAGE_REGISTERS = {
    40134: ("Battery Voltage", 1, "uint16", 0.1, "V", "voltage"),
    # Format: address -> (name, register_count, type, scale, unit, device_class)
}
```

Register types: `uint16`, `int16`, `uint32`, `enum16`

## License

See [LICENSE](LICENSE)

## References

- [APstorage Modbus Documentation](https://per.pe/APstorage-Modbus.pdf)
- [Home Assistant Sensor Component](https://www.home-assistant.io/integrations/sensor/)
- [pymodbus Library](https://pymodbus.readthedocs.io/)
