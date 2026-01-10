"""Constants for the APstorage integration."""
from datetime import timedelta

DOMAIN = "apstorage"
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)

CONF_UNIT = "unit"
CONF_REGISTERS = "registers"
CONF_CONNECTION_TYPE = "connection_type"
CONF_BAUDRATE = "baudrate"

CONNECTION_TCP = "tcp"
CONNECTION_RTU = "rtu"

# APstorage Modbus register definitions (Holding registers)
# Format: address -> (name, read_count, value_type, scale_factor, unit_of_measurement, device_class)

APSTORAGE_REGISTERS = {
    40134: ("Battery Voltage", 1, "uint16", 0.1, "V", "voltage"),
    40114: ("DC Current", 1, "int16", 0.1, "A", "current"),
    40117: ("Battery Power", 1, "int16", 1, "W", "power"),
    40081: ("State of Charge (SoC)", 1, "uint16", 0.1, "%", "battery"),
    40083: ("State of Health (SoH)", 1, "uint16", 1, "%", None),
    40156: ("Battery Temperature", 1, "int16", 0.1, "°C", "temperature"),
    40157: ("PCS Temperature", 1, "int16", 0.1, "°C", "temperature"),
    40086: ("Charge Status", 1, "enum16", 1, None, None),
    40135: ("Active Power Phase A", 1, "int16", 1, "W", "power"),
    40136: ("Active Power Phase B", 1, "int16", 1, "W", "power"),
    40137: ("Active Power Phase C", 1, "int16", 1, "W", "power"),
    40138: ("Reactive Power Phase A", 1, "uint16", 1, "Var", None),
    40139: ("Reactive Power Phase B", 1, "uint16", 1, "Var", None),
    40140: ("Reactive Power Phase C", 1, "uint16", 1, "Var", None),
    40146: ("Daily Charge Energy", 1, "uint16", 0.01, "kWh", "energy"),
    40147: ("Daily Discharge Energy", 1, "uint16", 0.01, "kWh", "energy"),
    40148: ("Charge Energy", 2, "uint32", 0.01, "kWh", "energy"),
    40150: ("Discharge Energy", 2, "uint32", 0.01, "kWh", "energy"),
    40153: ("Grid Power Phase A", 1, "int16", 1, "W", "power"),
    40154: ("Grid Power Phase B", 1, "int16", 1, "W", "power"),
    40155: ("Grid Power Phase C", 1, "int16", 1, "W", "power"),
    40073: ("Energy Capacity (WHRtg)", 1, "uint16", 0.01, "kWh", "energy"),
    40074: ("Max Charge Rate", 1, "uint16", 1, "W", "power"),
    40075: ("Max Discharge Rate", 1, "uint16", 1, "W", "power"),
    40089: ("Controller Heartbeat", 1, "uint16", 1, None, None),
    40183: ("Set Power", 1, "int16", 1, "W", "power"),
}

# Writable registers (address -> max_value for validation)
APSTORAGE_WRITABLE_REGISTERS = {
    40183: 10000,  # Set Power: max 10000W
}

CHARGE_STATUS_ENUM = {
    1: "OFF",
    2: "EMPTY",
    3: "DISCHARGING",
    4: "CHARGING",
    5: "FULL",
    6: "HOLDING",
    7: "TESTING",
}
