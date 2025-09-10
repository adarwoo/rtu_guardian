import asyncio
import re
from enum import Enum, auto

from textual.widgets import TabPane, Tab
from textual.containers import Container
from textual.reactive import reactive
from textual.worker import Worker

from pymodbus.pdu import ModbusPDU

from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.modbus.request import ReportDeviceId, ReadDeviceInformation

CSS_KNOWN_DEVICE = "known-device"
CSS_UNKNOWN_DEVICE = "unknown-device"
CSS_DISCONNECTED_DEVICE = "disconnected-device"


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


class Device(TabPane):
    """
    The device is the TabPane which owns a given device.
    The content area defaults to the device's status text until the device
    type is established - then the content becomes substituted with the correct
    type.
    The Device handles all outgoing communication with the device, through the
    agent.
    """
    title = reactive("?")
    status_text = reactive("Scanning for device...")

    def __init__(self, device_id: int, modbus_agent: ModbusAgent):
        super().__init__(f"?@{device_id}", id=f"device-{device_id}")
        self.device_id = device_id
        self.modbus_agent = modbus_agent
        self.scanner = DeviceScanner(modbus_agent, device_id, self.update_callback)

    def on_mount(self):
        """
        Start scanning
        """
        # Use app to schedule; app reference is available after construction when added to TabbedContent
        self.run_worker(self.scanner.start(), name=f"identify-{self.device_id}")

    def set_title_prefix(self, name: str, class_to_use: str):
        """ Set the title prefix for the device tab """
        tab = self.app.query_one("#devices").query_one(
            f"#--content-tab-device-{self.device_id}", Tab
        )

        tab.reset_styles()
        tab.add_class(class_to_use)
        tab.label = f"{name}@{self.device_id}"

    def update_callback(self, state: DeviceState, status_text: str):
        self.status_text = status_text

        if state == DeviceState.IDENTIFIED:
            self.set_title_prefix(self.title, CSS_KNOWN_DEVICE)
            self.remove_children()   # wipe old status
            self.mount(DeviceFactory.create_device_container(self.scanner.device_id))

        elif state == DeviceState.UNKNOWN:
            self.set_title_prefix("unknown", CSS_UNKNOWN_DEVICE)

        elif state == DeviceState.NO_REPLY:
            self.set_title_prefix("away", CSS_DISCONNECTED_DEVICE)
            # Keep trying to identify
            self.run_worker(self.scanner.start(), name=f"identify-{self.device_id}")

    def render(self):
        # Simple textual status for now
        return self.status_text


class DeviceScanner:
    """ Scans a device to identify it, calling back to the device with updates
    """
    def __init__(self, modbus_agent: ModbusAgent, device_address: int, update_callback: callable):
        """ Initialize the scanner 
        :param modbus_agent: The ModbusAgent to use for requests
        :param device_address: The Modbus address of the device to scan
        :param update_callback: A callable taking (DeviceState, status_text) to call with updates
        """
        self.modbus_agent = modbus_agent
        self.device_address = device_address
        self.update_callback = update_callback  # Should be a callable taking a DeviceState
        self.stage = ScannerStage.INITIAL
        self.state = DeviceState.QUERYING
        self.device_id = None
        self.status_text = ""

    async def start(self):
        """ Start the scanning process. This is a coroutine since it can wait"""
        # If we're re-entering after no reply, wait a bit
        if self.stage == ScannerStage.NO_REPLY:
            await asyncio.sleep(2)
            self.stage = ScannerStage.INITIAL

        if self.stage == ScannerStage.INITIAL:
            self.stage = ScannerStage.REQUESTED_DEVICEID
            self.status_text = f"Attempting to identify device at address {self.device_address}..."
            self.update_callback(self.state, self.status_text)

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
        id = pdu.identifier[0]
        name = pdu.identifier[2:]
        name = name.decode("ascii", errors="ignore")

        # Pass the ID and name to the factory
        if not DeviceFactory.identify_device(name=name, id=id):
            # Treat like an error to move on to MEI
            self._on_device_id_error()
        else:
            self.stage = ScannerStage.DONE
            self.state = DeviceState.IDENTIFIED
            self.status_text = f"Identified as {name} ({id})"
            self.update_callback(self.state, self.status_text)

    def _on_device_id_error(self, exception_code: int):
        self.stage = ScannerStage.REQUESTED_MEI
        self.status_text = "Attempting to read device information"
        self.update_callback(self.state, self.status_text)

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
        self.update_callback(self.state, self.status_text)

    def _on_device_info_error(self, exception_code: int):
        self.status_text = "Malformed device information"
        self.stage = ScannerStage.DONE
        self.state = DeviceState.UNKNOWN
        self.update_callback(self.state, self.status_text)

    def _on_device_info(self, pdu: ModbusPDU):
        self.stage = ScannerStage.DONE
        
        # Decode the PDU
        try:
            identifier = pdu.identifier
            dev_id = identifier[0]
            name_bytes = identifier[2:]
            dev_name = name_bytes.decode("ascii", errors="ignore")

            if not DeviceFactory.identify_device(name=dev_name, id=dev_id):
                self.state = DeviceState.UNKNOWN
                self.status_text = "Unknown device"
            else:
                self.state = DeviceState.IDENTIFIED
                self.status_text = f"Identified as {dev_name} ({dev_id})"
                
        except Exception:
            self.status_text = "Malformed device information"
            self.state = DeviceState.UNKNOWN
        
        self.update_callback(self.state, self.status_text)


class DeviceFactory:
    """ Factory to create devices based on ID and name """

    @staticmethod
    def identify_device(*, name: str="", id: int=0) -> str:
        """ Identify the device based on ID and name """
        if id == 44:
            return "MBR-ES"
        elif re.match(r"^CONSOLE", name, re.IGNORECASE):
            return "console"
        elif re.match(r"^PNEUMATIC", name, re.IGNORECASE):
            return "pneumatic"

        return None

    @staticmethod
    def create_device_container(device_id: str, device_address: int, modbus_agent: ModbusAgent) -> Container:
        container = DeviceFactory._get_device_container(device_id)

        if container is not None:
            return container(modbus_agent, device_address)

    @staticmethod
    def _get_device_container(name) -> Container | None:
        """ Return the device container if known """
        if name == "MBR-ES":
            from rtu_guardian.devices.relay_es.relay_device import RelayDevice
            return RelayDevice
        elif name == "console":
            from rtu_guardian.devices.console.console_device import ConsoleDevice
            return ConsoleDevice
        elif name == "pneumatic":
            from rtu_guardian.devices.pneumatic.pneumatic_device import PneumaticDevice
            return PneumaticDevice

        return None    