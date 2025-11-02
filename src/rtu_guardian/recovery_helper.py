import re
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
from rtu_guardian.constants import RECOVERY_ID
from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.modbus.request import ReadDeviceInformation, ReadHoldingRegisters
from rtu_guardian.config import config, VALID_BAUD_RATES
from pymodbus.pdu.mei_message import ReadDeviceInformationResponse


from rtu_guardian.constants import (
    VENDOR_NAME_OBJECT_CODE,
    PRODUCT_CODE_OBJECT_CODE,
    REVISION_OBJECT_CODE,
    MODEL_NAME_OBJECT_CODE,
    RECOVERY_MODE_OBJECT_CODE
)

MAP_BAUD_RATES = {
    0: 300, 1: 600, 2: 1200, 3: 2400, 4: 4800, 5: 9600, 6: 19200, 7: 38400, 8: 57600, 9: 115200
}

PARITY_MAP = { 0: "N", 1: "O", 2: "E" }

def parity_to_string(parity: int|str) -> str:
    if isinstance(parity, str):
        p = parity.strip().lower()
        if p in ("none", "n"):
            return "None"
        if p in ("even", "e"):
            return "Even"
        if p in ("odd", "o"):
            return "Odd"
        return parity
    return PARITY_MAP.get(parity, "None")

class CommParams:
    def __init__(self, version: int, pdu: ReadHoldingRegisters):
        self.version = version
        self.raw_data = pdu.registers
        self.device_id: int = 0
        self.baudrate: int = 0
        self.parity: str = 'N'
        self.stopbits: int = 1

        self.error_message: List[str] = []

        if version == 1:
            self.from_payload_ver1(pdu)
        else:
            self.error_message.append(f"Unsupported recovery protocol version: {version}")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "baudrate": self.baudrate,
            "parity": self.parity,
            "stopbits": self.stopbits,
        }

    def validate(self):
        if self.baudrate not in VALID_BAUD_RATES:
            raise ValueError(f"Invalid baudrate: {self.baudrate}")
        if self.parity not in ['N', 'E', 'O']:
            raise ValueError(f"Invalid parity: {self.parity}")
        if self.stopbits not in [1, 2]:
            raise ValueError(f"Invalid stopbits: {self.stopbits}")

    def from_payload_ver1(self, pdu: ReadHoldingRegisters):
        self.device_id = pdu.registers[0]
        self.baudrate = pdu.registers[1]
        self.parity = pdu.registers[2]
        self.stop_bits = pdu.registers[3]

        if self.baudrate in MAP_BAUD_RATES.keys():
            self.baudrate = MAP_BAUD_RATES[self.baudrate]
        else:
            self.error_message.append(f"Invalid baud rate: {self.baudrate}")

        if pdu.registers[2] in PARITY_MAP:
            self.parity = PARITY_MAP[pdu.registers[2]]
        else:
            self.error_message.append(f"Invalid parity: {pdu.registers[2]}")

        if pdu.registers[3] in [1, 2]:
            self.stop_bits = pdu.registers[3]
        else:
            self.error_message.append(f"Invalid stop bits: {pdu.registers[3]}")

    def composite_serial_params(self) -> str:
        """Return a tuple of (baudrate, parity, stopbits) for serial client."""
        return f"{self.baudrate} 8{self.parity}{self.stopbits}"

class RecoveryInterface:
    def on_error(self, message: str):
        pass

    def on_comm_params(self, comm_params: CommParams):
        pass


class RecoveryHelper:
    """
    Abstract recovery data based on the recovery protocol version.
    Provides:
      - decoding register map -> CommParams
      - encoding CommParams -> registers
    Usage:
      helper = RecoveryHelper("1.0")
      params = helper.decode_registers({1: 2, 2: 1, 3: 8, 4: 0})
      regmap = helper.encode_params(params)
      schema = helper.get_hmi_schema()
    """

    def __init__(self, processor: RecoveryInterface, pdu: ReadDeviceInformationResponse):
        self.processor = processor
        self.info = { "supported": False, "version": 0, "config_address": 0 }

        # Extract values and their corresponding coordinates
        info_map = {
            VENDOR_NAME_OBJECT_CODE:   "vendor_name",
            PRODUCT_CODE_OBJECT_CODE:  "product_code",
            REVISION_OBJECT_CODE:      "revision",
            MODEL_NAME_OBJECT_CODE:    "model_name",
            RECOVERY_MODE_OBJECT_CODE: "recovery_mode_string"
        }

        for obj_code, label in info_map.items():
            self.info[label] = pdu.information.get(obj_code, b"").decode('ascii').strip()

        # Does the device report supporting MEI object code 0x80 (recovery mode)?
        if len(self.info["recovery_mode_string"]) > 0:
            # Parse the recovery to make sure it is compatible
            # The format is 'ReCoVeRy;<ver>;<config holding reg address in hex>'
            raw_info = self.info["recovery_mode_string"]

            m = re.match(
                r'^\s*ReCoVeRy\s*;\s*(\d+)\s*;\s*(0x[0-9A-Fa-f]{4})\s*$',
                raw_info,
                re.IGNORECASE)

            if m:
                self.info["version"] = int(m.group(1))
                self.info["config_address"] = int(m.group(2), 16)

                if self.info["version"] >= 1:
                    self.info["supported"] = True

        # How many registers to read for config?
        self.info["count"] = 4 if self.info["version"] == 1 else 0

        # Make an accessor method for every key of the info a property for easier access
        for key in self.info.keys():
            setattr(self, key, self.info.get(key, None))

    def on_config_result(self, registers):
        """Handle received holding registers and decode to CommParams."""
        params = CommParams(self.version, registers)

        if ( len(params.error_message) > 0 ):
            error_msg = "\n".join(params.error_message)
            self.processor.on_error(error_msg)
        else:
            self.processor.on_comm_params(params)

    def ready_values(self, values: Dict) -> bool:
        """ Return an array with the holding register values for recovery mode writing. """

        required_fields = ('device_id', 'baudrate', 'parity', 'stopbits')
        missing = [f for f in required_fields if f not in values]
        if missing:
            raise KeyError(f"Missing required recovery fields: {', '.join(missing)}")

        device_id = values['device_id']
        baudrate = values['baudrate']
        parity = values['parity']
        stopbits = values['stopbits']

        # Convert to register values based on version
        if self.version == 1:
            baudrate_code = None
            for code, rate in MAP_BAUD_RATES.items():
                if rate == baudrate:
                    baudrate_code = code
                    break
            if baudrate_code is None:
                raise ValueError(f"Invalid baudrate for recovery mode: {baudrate}")

            parity_code = None
            for code, p in PARITY_MAP.items():
                if p == parity:
                    parity_code = code
                    break
            if parity_code is None:
                raise ValueError(f"Invalid parity for recovery mode: {parity}")

            return [
                device_id,
                baudrate_code,
                parity_code,
                stopbits
            ]

        raise ValueError(f"Unsupported recovery protocol version: {self.version}")
