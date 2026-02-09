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
    # Device Information
    40002: ("Model ID", 1, "uint16", 1, None, None),
    40003: ("Model Length", 1, "uint16", 1, None, None),
    40004: ("Manufacturer", 16, "string", 1, None, None),
    40020: ("Model", 16, "string", 1, None, None),
    40036: ("Options", 8, "string", 1, None, None),
    40044: ("Version", 8, "string", 1, None, None),
    40052: ("Serial Number", 16, "string", 1, None, None),
    40068: ("Device Address", 1, "uint16", 1, None, None),
    40070: ("Model ID 802", 1, "uint16", 1, None, None),
    40071: ("Model Length 128", 1, "uint16", 1, None, None),
    
    # Battery Specifications
    40073: ("Energy Capacity (WHRtg)", 1, "uint16", 0.01, "kWh", "energy"),
    40074: ("Max Charge Rate", 1, "uint16", 1, "W", "power"),
    40075: ("Max Discharge Rate", 1, "uint16", 1, "W", "power"),
    40077: ("SoC Max", 1, "uint16", 0.1, "%", None),
    40078: ("SoC Min", 1, "uint16", 0.1, "%", None),
    40079: ("SoC Reserve Max (SoCRsvMax)", 1, "uint16", 0.1, "%", None),
    40080: ("SoC Reserve Min (SoCRsvMin)", 1, "uint16", 0.1, "%", None),
    
    # Battery State
    40081: ("State of Charge (SoC)", 1, "uint16", 0.1, "%", "battery"),
    40083: ("State of Health (SoH)", 1, "uint16", 1, "%", None),
    40086: ("Charge Status", 1, "enum16", 1, None, None),
    40089: ("Controller Heartbeat", 1, "uint16", 1, None, None),
    
    # Alarms and Events
    40096: ("Battery Event 1 Bitfield", 2, "bitfield32", 1, None, None),
    40100: ("PCS Alarm Bitfield (EvtVnd1)", 2, "bitfield32", 1, None, None),
    
    # Voltage and Current
    40104: ("DC Bus Voltage", 1, "uint16", 0.1, "V", "voltage"),
    40114: ("DC Current", 1, "int16", 0.1, "A", "current"),
    40117: ("Battery Power", 1, "int16", 1, "W", "power"),
    40134: ("Battery Voltage", 1, "uint16", 0.1, "V", "voltage"),
    
    # AC Power - Active
    40135: ("Active Power Phase A", 1, "int16", 1, "W", "power"),
    40136: ("Active Power Phase B", 1, "int16", 1, "W", "power"),
    40137: ("Active Power Phase C", 1, "int16", 1, "W", "power"),
    
    # AC Power - Reactive
    40138: ("Reactive Power Phase A", 1, "uint16", 1, "Var", None),
    40139: ("Reactive Power Phase B", 1, "uint16", 1, "Var", None),
    40140: ("Reactive Power Phase C", 1, "uint16", 1, "Var", None),
    
    # Energy Tracking
    40146: ("Daily Charge Energy", 1, "uint16", 0.01, "kWh", "energy"),
    40147: ("Daily Discharge Energy", 1, "uint16", 0.01, "kWh", "energy"),
    40148: ("Charge Energy", 2, "uint32", 0.01, "kWh", "energy"),
    40150: ("Discharge Energy", 2, "uint32", 0.01, "kWh", "energy"),
    
    # Grid Power
    40153: ("Grid Power Phase A", 1, "int16", 1, "W", "power"),
    40154: ("Grid Power Phase B", 1, "int16", 1, "W", "power"),
    40155: ("Grid Power Phase C", 1, "int16", 1, "W", "power"),
    
    # Temperature
    40156: ("Battery Temperature", 1, "int16", 0.1, "°C", "temperature"),
    40157: ("PCS Temperature", 1, "int16", 0.1, "°C", "temperature"),
    
    # Firmware Versions
    40159: ("Chip1 Version", 8, "string", 1, None, None),
    40167: ("Chip2 Version", 8, "string", 1, None, None),
    40175: ("Chip3 Version", 8, "string", 1, None, None),
    
    # Control
    40183: ("Set Power", 1, "int16", 1, "W", "power"),
}

# Writable registers (address -> UI metadata)
APSTORAGE_WRITABLE_REGISTERS = {
    40068: {"min": 1, "max": 247, "step": 1, "mode": "box"},  # Device Address
    40079: {"min": 0, "max": 100, "step": 0.1, "mode": "slider"},  # SoC Reserve Max
    40080: {"min": 0, "max": 100, "step": 0.1, "mode": "slider"},  # SoC Reserve Min
    40183: {"min": -10000, "max": 10000, "step": 1, "mode": "box"},  # Set Power
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

# Battery Event 1 Bitfield alarm definitions (address 40096)
BATTERY_ALARM_BITS = {
    0: "COMMUNICATION_ERROR",
    1: "OVER_TEMP_ALARM",
    3: "UNDER_TEMP_ALARM",
    5: "OVER_CHARGE_CURRENT_ALARM",
    7: "OVER_DISCHARGE_CURRENT_ALARM",
    9: "OVER_VOLT_ALARM",
    11: "UNDER_VOLT_ALARM",
    22: "GROUND_FAULT",
}

# PCS Alarm Bitfield definitions (address 40100)
PCS_ALARM_BITS = {
    0: "PCS_COMMUNICATION_ERROR",
    1: "AC_A_Voltage_stage1_Exceeding_Range",
    2: "AC_A_Voltage_stage1_Under_Range",
    3: "AC_B_Voltage_stage1_Exceeding_Range",
    4: "AC_B_Voltage_stage1_Under_Range",
    5: "AC_C_Voltage_stage1_Exceeding_Range",
    6: "AC_C_Voltage_stage1_Under_Range",
    7: "AC_A_Voltage_stage2_Exceeding_Range",
    8: "AC_A_Voltage_stage2_Under_Range",
    9: "AC_B_Voltage_stage2_Exceeding_Range",
    10: "AC_B_Voltage_stage2_Under_Range",
    11: "AC_C_Voltage_stage2_Exceeding_Range",
    12: "AC_C_Voltage_stage2_Under_Range",
    13: "AC_A_Voltage_stage3_Exceeding_Range",
    14: "AC_A_Voltage_stage3_Under_Range",
    15: "AC_B_Voltage_stage3_Exceeding_Range",
    16: "AC_B_Voltage_stage3_Under_Range",
    17: "AC_C_Voltage_stage3_Exceeding_Range",
    18: "AC_C_Voltage_stage3_Under_Range",
    19: "AC_A_Voltage_stage4_Exceeding_Range",
    20: "AC_A_Voltage_stage4_Under_Range",
    21: "AC_B_Voltage_stage4_Exceeding_Range",
    22: "AC_B_Voltage_stage4_Under_Range",
    23: "AC_C_Voltage_stage4_Exceeding_Range",
    24: "AC_C_Voltage_stage4_Under_Range",
}

# Diagnostic sensors (should be hidden by default in UI)
DIAGNOSTIC_REGISTERS = {
    40002, 40003, 40068, 40070, 40071,  # Model IDs and addresses
    40089,  # Heartbeat
    40096, 40100,  # Alarm bitfields
    40159, 40167, 40175,  # Chip versions
}

# Map value registers to their scale factor register (if any)
APSTORAGE_SCALE_REGISTERS = {
    40081: 40082,  # SoC uses SoC_SF
    40083: 40084,  # SoH uses SoH_SF
    40134: 40133,  # Battery Voltage uses V_SF (example, adjust as needed)
    40114: 40113,  # DC Current uses I_SF (example, adjust as needed)
    # Add more as needed based on documentation
}
