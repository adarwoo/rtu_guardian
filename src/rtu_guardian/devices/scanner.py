import asyncio
from enum import Enum, auto
from logging import Logger

from pymodbus.pdu import ModbusPDU

from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.modbus.request import ReportDeviceId, ReadDeviceInformation
from rtu_guardian.constants import (
    VENDOR_NAME_OBJECT_CODE,
    PRODUCT_CODE_OBJECT_CODE,
    REVISION_OBJECT_CODE,
    MODEL_NAME_OBJECT_CODE,
)

from pymodbus.pdu.mei_message import ReadDeviceInformationResponse

from .factory import factory, DiscoveredDevice
import re

logger = Logger("device")

class DeviceState(Enum):
    QUERYING = auto()    # Device is being queried
    UNKNOWN = auto()     # Device is unknown
    IDENTIFIED = auto()  # Device has been identified
    NO_REPLY = auto()    # Device did not reply

class ScannerStage(Enum):
    INITIAL = auto()
    REQUESTED_DEVICEID = auto()
    REQUESTED_MEI = auto()
    DONE = auto()

class DeviceView:
    """Interface for objects that can receive device scanning updates"""

    def on_update_status(self, state: DeviceState, status_text: str, is_final: bool):
        """Called when device scanning status changes

        :param state: The current device state
        :param status_text: Human readable status message
        :param is_final: Whether this is a final state (no more updates expected)
        """
        raise NotImplementedError("Subclasses must implement on_update_status")

class DeviceScanner:
    """ Scans a device to identify it, calling back to the device view with updates
    """
    def __init__(self, modbus_agent: ModbusAgent, device_address: int, device_view: DeviceView):
        """ Initialize the scanner
        :param modbus_agent: The ModbusAgent to use for requests
        :param device_address: The Modbus address of the device to scan
        :param device_view: Object implementing DeviceView interface for callbacks
        """
        self.device_view: DeviceView = device_view
        self.modbus_agent = modbus_agent
        self.device_address = device_address
        self.stage = ScannerStage.INITIAL
        self.state = DeviceState.QUERYING
        self.device_typeid = None
        self.status_text = ""
        self.device_info = {}
        self.candidates = []
        self.discovered_device: DiscoveredDevice | None = None

    @property
    def is_identified(self) -> bool:
        """Returns True if device has been successfully identified"""
        return self.state == DeviceState.IDENTIFIED and self.discovered_device is not None

    @property
    def is_complete(self) -> bool:
        """Returns True if scanning is complete (final state reached)"""
        return self.stage == ScannerStage.DONE

    @property
    def device_name(self) -> str | None:
        """Returns the device name if available"""
        return self.device_info.get("dev_name") or self.device_info.get("name")

    @property
    def device_type(self) -> str | None:
        """Returns the device type if identified"""
        return self.discovered_device.type if self.discovered_device else None

    @property
    def supports_recovery(self) -> bool:
        """Returns True if device supports recovery mode"""
        return "recovery_mode" in self.device_info

    @property
    def recovery_info(self) -> dict | None:
        """Returns recovery mode information if available"""
        return self.device_info.get("recovery_mode")

    def get_discovered_device(self) -> DiscoveredDevice | None:
        """Returns the discovered device if identified, None otherwise"""
        return self.discovered_device

    def get_device_info(self) -> dict:
        """Returns all collected device information"""
        return self.device_info.copy()

    async def start(self, skip_device_info: bool=False):
        """ Start the scanning process. This is a coroutine since it can wait"""
        # If we're re-entering after no reply, wait a bit
        if self.stage == ScannerStage.DONE:
            await asyncio.sleep(2)
            self.stage = ScannerStage.INITIAL

        if self.stage == ScannerStage.INITIAL:
            self.stage = ScannerStage.REQUESTED_DEVICEID
            self.status_text = f"Attempting to identify device at address {self.device_address}..."
            self.device_view.on_update_status(self.state, self.status_text, False)

            # Request the device ID
            self.modbus_agent.request(
                ReportDeviceId(
                    self.device_address,
                    self._on_device_id_report,
                    on_error=self._on_device_id_error,
                    on_no_response=self._on_no_response
                )
            )

    def _on_device_id_report(self, pdu: ModbusPDU):
        """ The device replied, but our factory cannot identify """
        # Decode the PDU
        self.device_info["id"] = pdu.identifier[0]
        name = pdu.identifier[2:]
        self.device_info["name"] = name.decode("ascii", errors="ignore")

        # Pass the ID and name to the factory
        self.candidates = factory.match(self.candidates, type="id", **self.device_info)

        if len(self.candidates) > 1: # More candidates - need MEI
            # Treat like an error to move on to MEI
            self._on_device_id_error()
        elif len(self.candidates) == 1:
            device = self.candidates[0]
            self.discovered_device = device
            self.device_typeid = device.type
            self.stage = ScannerStage.DONE
            self.state = DeviceState.IDENTIFIED
            self.status_text = f"Identified as {name} ({device.type})"
            self.device_view.on_update_status(self.state, self.status_text, True)

    def _on_device_id_error(self, exception_code: int = 0):
        self.stage = ScannerStage.REQUESTED_MEI
        self.status_text = "Attempting to read device information"
        self.device_view.on_update_status(self.state, self.status_text, False)

        # Request the device ID
        self.modbus_agent.request(
            ReadDeviceInformation(
                self.device_address,
                self._on_device_info,
                on_error=self._on_device_info_error,
                on_no_response=self._on_no_response
            )
        )

    def _on_no_response(self):
        self.status_text = "No response from device."
        self.stage = ScannerStage.DONE
        self.state = DeviceState.NO_REPLY
        self.device_view.on_update_status(self.state, self.status_text, True)

    def _on_device_info_error(self, exception_code: int):
        self.status_text = "Malformed device information"
        self.stage = ScannerStage.DONE
        self.state = DeviceState.UNKNOWN
        self.device_view.on_update_status(self.state, self.status_text, True)

    def _on_device_info(self, pdu: ReadDeviceInformationResponse):
        self.stage = ScannerStage.DONE

        # Decode the PDU
        try:
            # Extract values and their corresponding coordinates
            info_map = {
                VENDOR_NAME_OBJECT_CODE:      "vendor_name",
                PRODUCT_CODE_OBJECT_CODE:     "product_code",
                REVISION_OBJECT_CODE:         "revision",
                MODEL_NAME_OBJECT_CODE:       "model_name",
            }

            for obj_code, label in info_map.items():
                value = pdu.information.get(obj_code, b"").decode('ascii').strip()
                self.device_info[label] = value

            self.candidates = factory.match(self.candidates, type="id", **self.device_info)

            if len(self.candidates) == 0:
                self.state = DeviceState.UNKNOWN
                self.status_text = "Unknown device"
            elif len(self.candidates) > 1:
                self.state = DeviceState.UNKNOWN
                self.status_text = "Multiple matching device types"
            else:
                device = self.candidates[0]
                self.discovered_device = device
                self.device_typeid = device.type
                self.state = DeviceState.IDENTIFIED
                self.status_text = (
                    f"Identified as {self.device_info['dev_name']}"
                    f" ({self.device_info['device_id']})"
                )

        except Exception as e:
            self.status_text = "Malformed device information"
            self.state = DeviceState.UNKNOWN

        self.device_view.on_update_status(self.state, self.status_text, True)

