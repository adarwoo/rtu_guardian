from textual.containers import Container
from textual.widgets import DataTable, Button
from textual.containers import HorizontalGroup, Vertical, Grid, VerticalGroup
from textual.reactive import reactive

from rtu_guardian.modbus.agent import ModbusAgent


ROWS = [
    ("Expected type", "--"),
    ("[b magenta]Detected type", "--"),
    ("Lower voltage threshold", "0.0V"),
    ("[b magenta]Lowest measured voltage", "0.0V"),
    ("Upper voltage threshold", "300.0V"),
    ("[b magenta]Highest measured voltage", "300.0V"),
    ("Current voltage", "0.0V")
]


class InfeedWidget(VerticalGroup):
    min_input_voltage = reactive(0.0)
    max_input_voltage = reactive(0.0)
    current_input_voltage = reactive(0.0)

    def __init__(self, agent: ModbusAgent, device_address: int):
        super().__init__()
        self.agent = agent
        self.device_address = device_address

    def compose(self):
        yield DataTable(show_header=False, show_cursor=False)
        with HorizontalGroup():
            yield Button("Reset", id="infeed-reset-button")
            yield Button("Configure", id="infeed-config-button")

    def on_mount(self):
        self.border_title = f"Infeed"
        table = self.query_one(DataTable)
        table.add_columns(*ROWS[0])
        table.add_rows(ROWS)

