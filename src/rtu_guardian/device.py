
from pymodbus.constants import ExcCodes
from textual.widgets import TabPane
from textual.reactive import reactive
from enum import Enum, auto

from pymodbus.pdu import ModbusPDU

from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.modbus.request import ReportDeviceId, Request


class DeviceState(Enum):
    SCANNING = auto()
    UNKNOWN = auto()

class Device(TabPane):
    """
    The device is the TabPane which owns a given device.
    The content area defaults to the device's status text until the device
    type is established - then the content becomes substituted with the correct
    type.
    The Device handles all outgoing communication with the device, through the
    agent.
    """
    state = reactive(DeviceState.SCANNING)
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
        self.state = DeviceState.SCANNING
        self.status_text = "Trying to identify device..."

        # Request the device ID
        self.modbus_agent.request(
            ReportDeviceId(
                self.device_id,
                self.on_device_id_report,
                on_error=self.on_device_id_error,
                on_no_response=self.on_device_id_no_response
            )
        )

    def on_device_id_report(self, pdu: ModbusPDU):
        self.status_text = f"Identified device: {pdu}"
        # Decode the PDU

    def on_device_id_error(self, exception_code: int):
        if exception_code == ExcCodes.ILLEGAL_FUNCTION:
            self.status_text = "Found device"

    def on_device_id_no_response(self):
        self.status_text = "No response from device."

    def render(self):
        # Simple textual status for now
        return self.status_text

    def substitution_factory(self, ):
        from rtu_guardian.devices.es_relay.ui.device import Device as ESRelayDevice

        if self.device_id == 44:
            pane: TabPane = ESRelayDevice(id=f"device-{self.device_id}")
