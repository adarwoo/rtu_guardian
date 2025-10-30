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

#
# CSS classes for device list entries
#
CSS_KNOWN_DEVICE = "known-device"
CSS_UNKNOWN_DEVICE = "unknown-device"
CSS_DISCONNECTED_DEVICE = "disconnected-device"

#
# Modbus constants
#
RECOVERY_ID = 248
MODBUS_TIMEOUT = 0.2  # seconds

#
# MEI Object Codes
#
VENDOR_NAME_OBJECT_CODE = 0x00
PRODUCT_CODE_OBJECT_CODE = 0x01
REVISION_OBJECT_CODE = 0x02
VENDOR_URL_OBJECT_CODE = 0x03
PRODUCT_NAME_OBJECT_CODE = 0x04
MODEL_NAME_OBJECT_CODE = 0x05
USER_APPLICATION_NAME_OBJECT_CODE = 0x06
RECOVERY_MODE_OBJECT_CODE = 0x80
