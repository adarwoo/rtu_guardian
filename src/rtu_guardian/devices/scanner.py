import asyncio
from enum import Enum, auto
from logging import Logger

from pymodbus.pdu import ModbusPDU

from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.modbus.request import ReportDeviceId, ReadDeviceInformation
from pymodbus.pdu.mei_message import ReadDeviceInformationResponse

from .factory import factory

logger = Logger("device")

class DeviceState(Enum):
    QUERYING = auto()
    UNKNOWN = auto()
    IDENTIFIED = auto()
    NO_REPLY = auto()

class ScannerStage(Enum):
    INITIAL = auto()
    REQUESTED_DEVICEID = auto()
    REQUESTED_MEI = auto()
    DONE = auto()

class DeviceScanner:
    """ Scans a device to identify it, calling back to the device with updates
    """
    def __init__(self, modbus_agent: ModbusAgent, device_address: int, device):
        """ Initialize the scanner
        :param modbus_agent: The ModbusAgent to use for requests
        :param device_address: The Modbus address of the device to scan
        :param update_callback: A callable taking (DeviceState, status_text, is_final) to call with updates
        """
        from .device import Device  # avoid circular import

        self.device_view: Device = device
        self.modbus_agent = modbus_agent
        self.device_address = device_address
        self.stage = ScannerStage.INITIAL
        self.state = DeviceState.QUERYING
        self.device_typeid = None
        self.status_text = ""
        self.device_info = {}
        self.candidates = []

    async def start(self):
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
            self.type = device.type
            self.stage = ScannerStage.DONE
            self.state = DeviceState.IDENTIFIED
            self.status_text = f"Identified as {name} ({self.type})"
            self.device_view.on_device_identified(device)

    def _on_device_id_error(self, exception_code: int):
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
            identifier = pdu.identifier
            self.device_info["device_id"] = identifier[0]
            name_bytes = identifier[2:]
            self.device_info["dev_name"] = name_bytes.decode("ascii", errors="ignore")
            self.device_info.update(pdu.information)

            self.candidates = factory.match(self.candidates, type="id", **self.device_info)

            if len(self.candidates) == 0:
                self.state = DeviceState.UNKNOWN
                self.status_text = "Unknown device"
            elif len(self.candidates) > 1:
                self.state = DeviceState.UNKNOWN
                self.status_text = "Multiple matching device types"
            else:
                device = self.candidates[0]
                self.state = DeviceState.IDENTIFIED
                self.status_text = (
                    f"Identified as {self.device_info['dev_name']}"
                    f" ({self.device_info['device_id']})"
                )

        except Exception:
            self.status_text = "Malformed device information"
            self.state = DeviceState.UNKNOWN

        self.device_view.on_update_status(self.state, self.status_text, True)

