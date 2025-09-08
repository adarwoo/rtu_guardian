import asyncio
import re

from pymodbus.constants import ExcCodes
from textual.widgets import TabPane
from textual.reactive import reactive
from enum import Enum, auto

from pymodbus.pdu import ModbusPDU

from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.modbus.request import ReportDeviceId, ReadDeviceInformation


class DeviceState(Enum):
    INITIAL = auto()
    REQUESTED_DEVICEID = auto()
    REQUESTED_MEI = auto()
    UNKNOWN = auto()
    IDENTIFIED = auto()
    NO_REPLY = auto()


class Device(TabPane):
    """
    The device is the TabPane which owns a given device.
    The content area defaults to the device's status text until the device
    type is established - then the content becomes substituted with the correct
    type.
    The Device handles all outgoing communication with the device, through the
    agent.
    """
    state = reactive(DeviceState.INITIAL)
    status_text = reactive("Scanning for device...")

    def __init__(self, device_id: int, modbus_agent: ModbusAgent):
        super().__init__(f"Device: {device_id}", id=f"device-{device_id}")
        self.device_id = device_id
        self.modbus_agent = modbus_agent

    def on_mount(self):
        """
        Start the identification worker.
        """
        # Use app to schedule; app reference is available after construction when added to TabbedContent
        self.run_worker(self.identification_worker(), name=f"identify-{self.device_id}")

    async def identification_worker(self):
        if self.state == DeviceState.NO_REPLY:
            await asyncio.sleep(2)
            DeviceState.INITIAL

        if self.state == DeviceState.INITIAL:
            self.status_text = "Requesting device id..."
            self.state = DeviceState.REQUESTED_DEVICEID

            # Request the device ID
            self.modbus_agent.request(
                ReportDeviceId(
                    self.device_id,
                    self.on_device_id_report,
                    on_error=self.on_device_id_error,
                    on_no_response=self.on_no_response
                )
            )

    def on_device_id_report(self, pdu: ModbusPDU):
        """ The device replied, but our factory cannot identify """
        # Decode the PDU
        # TODO
        id = 0
        name = ""

        # Pass the ID and name to the factory
        if not self.process(id=id, name=name):
            self.status_text = f"Unknown device: {id}/{name}"
            self.state = DeviceState.UNKNOWN           

    def on_device_id_error(self, exception_code: int):
        self.status_text = "No device ID returned. Attempting to read device information"
        self.state = DeviceState.REQUESTED_MEI

        # Request the device ID
        self.modbus_agent.request(
            ReadDeviceInformation(
                self.device_id,
                self.on_device_info,
                on_error=self.on_device_info_error,
                on_no_response=self.on_no_response
            )
        )

    def on_no_response(self):
        self.status_text = "No response from device."
        self.state = DeviceState.NO_REPLY

        # Keep at it!
        self.run_worker(self.identification_worker(), name=f"identify-{self.device_id}")

    def on_device_info_error(self, exception_code: int):
        self.status_text = "Cannot identify device"
        self.state = DeviceState.UNKNOWN

    def on_device_info(self, pdu: ModbusPDU):
        """
        Process the device info
        """
        # Decode the PDU
        # TODO -> Should the request do it? Probably
        
        # Pass to the factory
        if not self.process(id=id, name=name):
            self.status_text = f"Unknown device: {id}/{name}"
            self.state = DeviceState.UNKNOWN           

    def render(self):
        # Simple textual status for now
        return self.status_text

    def process(self, *, name: str="", id: int=0 ):
        """ Process the information and substitute content is device is known """
        pane: TabPane = None

        if id == 44 or re.match("RELAY"):
            from rtu_guardian.devices.es_relay.ui.device import Device
            pane: TabPane = Device(id=f"device-{self.device_id}")
        elif ...:

        if pane:
            self.state = DeviceState.IDENTIFIED
            # Substitute!
            # TODO
