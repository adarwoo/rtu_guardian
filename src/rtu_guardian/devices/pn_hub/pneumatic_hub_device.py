import struct

from textual.containers import Container
from textual.widget import Text
from textual.widgets import Static, Switch, Rule, DataTable
from textual.containers import Grid, HorizontalGroup
from textual.reactive import reactive
from textual.coordinate import Coordinate

from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.modbus.request import ReadDeviceInformation, WriteCoils, ReadDiscreteInputs
from rtu_guardian.devices.utils import modbus_poller

from pymodbus.pdu.mei_message import ReadDeviceInformationResponse
from pymodbus.pdu import ModbusPDU

from rtu_guardian.constants import (
    VENDOR_NAME_OBJECT_CODE,
    PRODUCT_CODE_OBJECT_CODE,
    REVISION_OBJECT_CODE,
)

# Pneumatic Hub Controlling outputs
# Position matches the coil index
outputs = [
    "Tool setter air blast",
    "Chuck clamp release",
    "Spindle clean",
    "Door push",
    "Door pull",
]

inputs = [
    "Low pressure alarm",
    "Water pump alarm",
]

ROWS = [
    "Vendor name",
    "Product code",
    "Revision",
]


class CustomPdu(ModbusPDU):
    function_code = 0x65 # 100

    def __init__(self, coils: list[bool] = None):
        super().__init__()
        self.coils = coils or []
        self.inputs = self.outputs = None

    def encode(self) -> bytes:
        """Encode a request pdu."""
        # Convert list of bools to a byte representing coil states
        coil_byte = 0

        for i, coil in enumerate(self.coils):
            if coil:
                coil_byte |= (1 << i)

        return struct.pack(">B", coil_byte)

    def decode(self, data: bytes) -> None:
        """Decode a request pdu."""
        self.outputs, self.inputs = struct.unpack(">B", data[:1])

    @classmethod
    def get_response_pdu_size(cls, buffer):
        # buffer includes function code + data
        # function code already known, so only data length
        return 1

    def decode(self, data):
        self.payload = data

@modbus_poller(interval=0.5)
class PneumaticHubDevice(Container):
    device_info = reactive("")

    def __init__(self, agent: ModbusAgent, device_address: int):
        super().__init__()
        self.agent = agent
        self.device_address = device_address

    def compose(self):
        with HorizontalGroup():
            yield DataTable(show_header=False, show_cursor=False)

            yield Rule(orientation="vertical")

            with Grid(id="pn-hub-ouptuts-grid"):
                for coil in range(len(outputs)):
                    yield Static(f"{outputs[coil]}", id=f"coil-{coil}-label")
                    yield Switch(id=f"coil-{coil}-switch")

            yield Rule(orientation="vertical")

            with Grid(id="pn-hub-inputs-grid"):
                for readout in range(len(inputs)):
                    yield Static(f"{inputs[readout]}", id=f"input-{readout}-label")
                    sw = Switch(id=f"input-{readout}-switch", disabled=True)
                    sw.can_focus = False
                    yield sw

    def on_mount(self):
        self.border_title = f"Pneumatic Hub"

        table = self.query_one(DataTable)
        table.add_columns("label", "value..............")
        table.zebra_stripes = True

        for row in ROWS:
            # Adding styled and justified `Text` objects instead of plain strings.
            styled_row = [
                Text(row, justify="right"),
                Text("-")
            ]

            table.add_row(*styled_row)

        # Request static device information (Requesting is instantaneous)
        self.agent.request(
            ReadDeviceInformation(self.device_address, self.on_device_information)
        )

    def on_device_information(self, pdu: ReadDeviceInformationResponse):
        """ Callback from ReadDeviceInformation """
        table = self.query_one(DataTable)

        # Extract values and their corresponding coordinates
        info_map = {
            VENDOR_NAME_OBJECT_CODE:      (0, "Vendor name"),
            PRODUCT_CODE_OBJECT_CODE:     (1, "Product code"),
            REVISION_OBJECT_CODE:         (2, "Revision"),
        }

        for obj_code, (row_idx, label) in info_map.items():
            value = pdu.information.get(obj_code, b"").decode('ascii').strip()
            table.update_cell_at(Coordinate(row_idx, 1), value)

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle switch toggle events for output coils."""
        # Only handle output switches, not input switches
        if event.switch.id and event.switch.id.startswith("coil-"):
            coil_states = []
            for coil in range(len(outputs)):
                sw = self.query_one(f"#coil-{coil}-switch", Switch)
                coil_states.append(sw.value)

            # Write the single coil state
            self.agent.request(
                WriteCoils(self.device_address, address=0, values=coil_states)
            )

    def on_poll(self):
        """ Read the inputs """

        # Create an bool array from the output switches
        self.agent.request(
            ReadDiscreteInputs(self.device_address, self.on_read_inputs, address=0, count=2)
        )

    def on_read_inputs(self, pdu: ModbusPDU):
        """ Process coil status """

        for readout in range(len(inputs)):
            sw = self.query_one(f"#input-{readout}-switch", Switch)
            sw.value = pdu.bits[readout]
