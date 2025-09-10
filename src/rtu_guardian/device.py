import asyncio
import re
from enum import Enum, auto

from textual.widgets import TabPane, TabbedContent, Tab
from textual.containers import Container
from textual.reactive import reactive

from pymodbus.pdu import ModbusPDU

from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.modbus.request import ReportDeviceId, ReadDeviceInformation

CSS_KNOWN_DEVICE = "known-device"
CSS_UNKNOWN_DEVICE = "unknown-device"
CSS_DISCONNECTED_DEVICE = "disconnected-device"


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
    title = reactive("?")
    state = reactive(DeviceState.INITIAL)
    status_text = reactive("Scanning for device...")

    def __init__(self, device_id: int, modbus_agent: ModbusAgent):
        super().__init__(f"?@{device_id}", id=f"device-{device_id}")
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
        id = pdu.identifier[0]
        state = pdu.identifier[1]
        name = pdu.identifier[2:]
        name = name.decode("ascii", errors="ignore")

        # Pass the ID and name to the factory
        if not self.process_and_substitute(id=id, name=name):
            self.on_device_id_error()

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
        # Update the title to reflect the device
        self.set_title_prefix("unknown", CSS_UNKNOWN_DEVICE)
        self.status_text = "No response from device."
        self.state = DeviceState.NO_REPLY

        # Keep at it!
        self.run_worker(self.identification_worker(), name=f"identify-{self.device_id}")

    def on_device_info_error(self, exception_code: int):
        self.set_title_prefix("unknown", CSS_UNKNOWN_DEVICE)
        self.status_text = "Cannot identify device"
        self.state = DeviceState.UNKNOWN

    def on_device_info(self, pdu: ModbusPDU):
        """
        Process the device info
        """
        # Decode the PDU
        try:
            identifier = pdu.identifier
            dev_id = identifier[0]
            name_bytes = identifier[2:]
            dev_name = name_bytes.decode("ascii", errors="ignore")

            if not self.process_and_substitute(id=dev_id, name=dev_name):
                self.status_text = "Unknown device"
                self.state = DeviceState.UNKNOWN
                self.set_title_prefix("unknown", CSS_UNKNOWN_DEVICE)
        except Exception:
            self.status_text = "Malformed device information"
            self.state = DeviceState.UNKNOWN
            self.set_title_prefix("unknown", CSS_UNKNOWN_DEVICE)


        # Pass to the factory
            pass

    def render(self):
        # Simple textual status for now
        return self.status_text

    def set_title_prefix(self, name: str, class_to_use: str):
        """ Set the title prefix for the device tab """
        tab = self.app.query_one("#devices").query_one(
            f"#--content-tab-device-{self.device_id}", Tab
        )

        tab.reset_styles()
        tab.add_class(class_to_use)

        tab.label = f"{name}@{self.device_id}"

    def process_and_substitute(self, *, name: str="", id: int=0 ):
        """ Process the information and substitute content is device is known """
        pane = None

        if id == 44 and re.match(r"MBR\d{1,2}-ES", name):
            from rtu_guardian.devices.relay_es.relay_device import RelayDevice

            # Create the device widget
            pane = RelayDevice(self.modbus_agent, self.device_id)

            # Trim the version from the name
            name = name[:name.find('-ES') + 3]

        # TODO Add more as required

        if pane:
            self.set_title_prefix(name, CSS_KNOWN_DEVICE)
            self.state = DeviceState.IDENTIFIED

            self.remove_children()   # wipe old status
            self.mount(pane) # Replace with device-specific UI (container)

        return pane is not None