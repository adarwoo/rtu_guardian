from typing import Optional, TypeVar

from textual.widgets import DataTable, Button
from textual.widget import Widget
from textual.containers import HorizontalGroup, Vertical

from rtu_guardian.device import Device
from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.modbus.request import ReadDeviceInformation

from .static_status_list import StaticStatusList


ROWS = [
    ("Vendor name", "--"),
    ("Product code", "--"),
    ("Revision", "0.0V"),
    ("Vendor URL", "0.0V"),
    ("Model name", "300.0V"),
    ("Number of relays", "3"),
    ("[magenta]Running hours", "23232'23"),
]

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
        table.add_columns(*ROWS[0])
        table.add_rows(ROWS)
        selection = self.query_one(StaticStatusList)
        selection.border_title = "Faults"
        selection.bin_status = 0b0000010101

        self.run_worker(self.collect_info_worker(), name=f"query-info")

    async def collect_info_worker(self):
        # Start a worker to get the static data
        self.agent.request(
            ReadDeviceInformation(self.device_address)
        )
