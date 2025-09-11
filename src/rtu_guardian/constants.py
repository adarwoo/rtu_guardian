# constants.py

# Valid baud values
VALID_BAUD_RATES = [300, 600, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]

APP_NAME = "rtu_guardian"
CONFIG_FILENAME = "config.toml"

# Config schema with defaults
CONFIG_SCHEMA = {
    "com_port": "", # Empty string means ask on startup
    "baud": 9600,
    "stop": 1,
    "parity": "N",
    "device_ids": [],
    "check_comm": True
}


CSS_KNOWN_DEVICE = "known-device"
CSS_UNKNOWN_DEVICE = "unknown-device"
CSS_DISCONNECTED_DEVICE = "disconnected-device"

#
# Modbus constants
#
RECOVERY_ID = 247
