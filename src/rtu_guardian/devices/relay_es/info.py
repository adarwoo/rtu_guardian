from textual.widgets import DataTable, Button
from textual.widget import Text
from textual.containers import HorizontalGroup, Vertical

from pymodbus.pdu.mei_message import ReadDeviceInformationResponse

from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.modbus.request import ReadDeviceInformation

from .static_status_list import StaticStatusList


ROWS = [
    "Vendor name",
    "Product code",
    "Revision",
    "Vendor URL",
    "Model name",
    "Number of relays",
    "Running hours"
]

VENDOR_NAME_OBJECT_CODE = 0x00
PRODUCT_CODE_OBJECT_CODE = 0x01
REVISION_OBJECT_CODE = 0x02
VENDOR_URL_OBJECT_CODE = 0x03
PRODUCT_NAME_OBJECT_CODE = 0x04
MODEL_NAME_OBJECT_CODE = 0x05
USER_APPLICATION_NAME_OBJECT_CODE = 0x06
NUMBER_OF_RELAYS_OBJECT_CODE = 0x80


class InfoWidget(HorizontalGroup):
    def __init__(self, agent: ModbusAgent, device_address: int):
        super().__init__()
        self.agent = agent
        self.device_address = device_address

    def compose(self):
        with Vertical():
            yield DataTable(show_header=False, show_cursor=False)
            yield Button("Identify")

        yield StaticStatusList([
            "Relay fault",
            "Infeed polarity",
            "Voltage type",
            "Low infeed",
            "High infeed",
            "Application crash",
            "EEProm recovered",
            "Supply voltage failure",
        ])

    def on_mount(self):
        self.border_title = f"Device info"

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

        selection = self.query_one(StaticStatusList)
        selection.border_title = "Faults"
        selection.bin_status = 0

        self.run_worker(self.collect_info_worker(), name=f"query-info")

    async def collect_info_worker(self):
        # Start a worker to get the static data
        self.agent.request(
            ReadDeviceInformation(self.device_address, self.on_reply, read_code=0x03)
        )

    def on_reply(self, pdu: ReadDeviceInformationResponse):
        """ Callback from ReadDeviceInformation """
        from textual.coordinate import Coordinate

        table = self.query_one(DataTable)

        # Extract values and their corresponding coordinates
        info_map = {
            VENDOR_NAME_OBJECT_CODE:      (0, "Vendor name"),
            PRODUCT_CODE_OBJECT_CODE:     (1, "Product code"),
            REVISION_OBJECT_CODE:         (2, "Revision"),
            VENDOR_URL_OBJECT_CODE:       (3, "Vendor URL"),
            MODEL_NAME_OBJECT_CODE:       (4, "Model name"),
            NUMBER_OF_RELAYS_OBJECT_CODE: (5, "Number of relays"),
        }

        for obj_code, (row_idx, label) in info_map.items():
            value = pdu.information.get(obj_code, b"").decode('ascii').strip()
            table.update_cell_at(Coordinate(row_idx, 1), value)
