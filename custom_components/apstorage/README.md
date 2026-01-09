# APstorage Modbus Custom Integration

Home Assistant custom integration for APstorage battery systems via Modbus TCP/RTU.

## Features

- **Real-time Monitoring**: Battery voltage, current, power, SoC, SoH
- **Temperature Sensors**: Battery and PCS temperatures
- **Energy Tracking**: Daily and cumulative charge/discharge energy
- **Grid Integration**: 3-phase active/reactive power monitoring
- **Flexible Connection**: Modbus TCP (default) or RTU (serial) support
- **Configurable Polling**: Adjustable scan interval (default 30s)

## Installation

1. Copy the `custom_components/apstorage` folder to your Home Assistant config directory:
   ```bash
   mkdir -p /path/to/config/custom_components/apstorage
   cp -r custom_components/apstorage/* /path/to/config/custom_components/apstorage/
   ```

2. Install dependencies (if not auto-installed by Home Assistant):
   ```bash
   pip install pymodbus==2.5.3
   ```

3. Restart Home Assistant

## Configuration

### YAML Configuration (configuration.yaml)

#### Modbus TCP (default)
```yaml
apstorage:
  host: 192.168.1.50
  port: 502
  unit: 1
  connection_type: tcp
  scan_interval: 30
```

#### Modbus RTU (Serial)
```yaml
apstorage:
  host: /dev/ttyUSB0        # or COM3 on Windows
  unit: 1
  connection_type: rtu
  baudrate: 9600
  scan_interval: 30
```

### Parameters

| Parameter | Description | Default | Required |
|-----------|-------------|---------|----------|
| `host` | IP address (TCP) or serial port path (RTU) | - | Yes |
| `port` | Modbus TCP port | 502 | No (TCP only) |
| `unit` | Modbus unit ID | 1 | No |
| `connection_type` | `tcp` or `rtu` | tcp | No |
| `baudrate` | Serial baud rate | 9600 | No (RTU only) |
| `scan_interval` | Polling interval in seconds | 30 | No |

## Exposed Sensors

The integration automatically creates sensors for the following APstorage registers:

| Sensor | Unit | Device Class |
|--------|------|--------------|
| Battery Voltage | V | voltage |
| DC Current | A | current |
| Battery Power | W | power |
| State of Charge (SoC) | % | battery |
| State of Health (SoH) | % | - |
| Battery Temperature | °C | temperature |
| PCS Temperature | °C | temperature |
| Charge Status | - | - |
| Active Power Phase A/B/C | W | power |
| Reactive Power Phase A/B/C | Var | - |
| Daily Charge Energy | kWh | energy |
| Daily Discharge Energy | kWh | energy |
| Charge Energy | kWh | energy |
| Discharge Energy | kWh | energy |
| Grid Power Phase A/B/C | W | power |
| Energy Capacity | kWh | energy |
| Max Charge Rate | W | power |
| Max Discharge Rate | W | power |
| Controller Heartbeat | - | - |

## Troubleshooting

### Connection Issues
- Verify network connectivity: `ping <host>`
- Check Modbus port: `netstat -an | grep :502`
- Confirm unit ID matches device configuration (typically 1)

### Serial (RTU) Connection
- Verify port exists: `ls -la /dev/ttyUSB*` (Linux/Mac) or check Device Manager (Windows)
- Correct baud rate must match device (usually 9600)
- Ensure proper permissions: `sudo usermod -a -G dialout $USER` (Linux)

### No Sensor Data
- Check Home Assistant logs: `<config>/home-assistant.log`
- Verify register addresses match APstorage documentation: https://per.pe/APstorage-Modbus.pdf
- Ensure device responds to Modbus queries (use external Modbus client to test)

## Advanced

### Custom Register Mapping

To add or modify registers, edit [const.py](const.py):

```python
APSTORAGE_REGISTERS = {
    40134: ("Battery Voltage", 1, "uint16", 0.1, "V", "voltage"),
    # (address, (name, count, type, scale, unit, device_class))
}
```

Register types: `uint16`, `int16`, `uint32`, `enum16`

## References

- APstorage Modbus Documentation: https://per.pe/APstorage-Modbus.pdf
- Home Assistant Sensor Component: https://www.home-assistant.io/integrations/sensor/
- pymodbus Documentation: https://pymodbus.readthedocs.io/
