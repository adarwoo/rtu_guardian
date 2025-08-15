from textual.containers import Container
from textual.widgets import DataTable, Button, SelectionList, Input, Rule, Static
from textual.containers import VerticalGroup, HorizontalGroup, Vertical, Horizontal
from textual.reactive import reactive

from .static_status_list import StaticStatusList


ROWS = [
    ("Status", "--"),
    ("Diagnostic code", "--")
]

class EStopWidget(VerticalGroup):
    def compose(self):
        with HorizontalGroup():
            with VerticalGroup():
                yield DataTable(show_header=False, show_cursor=False)
                yield Button("Clear", id="estop-clear-button")

            yield StaticStatusList([
                "Relay fault",
                "Modbus comm loss",
                "Infeed polarity",
                "Voltage type",
                "Low infeed",
                "High infeed",
                "External EStop",
                "Application crash",
                "EEProm recovered",
                "Supply voltage failure",
            ])

        yield Rule(line_style="heavy")

        with HorizontalGroup(id="estop-cmd-code-group"):
            yield Static("Code")
            yield Input(type="integer", placeholder="0-255", id="ext_diag_code")

        with HorizontalGroup():
            yield Button("Pulse", id="estop-pulse-button")
            yield Button("Set", id="estop-set-button")
            yield Button("Terminal", id="estop-terminal-button")

    def on_mount(self):
        self.border_title = f"EStop"
        table = self.query_one(DataTable)
        table.add_columns(*ROWS[0])
        table.add_rows(ROWS)
        faultlist = self.query_one(StaticStatusList)
        faultlist.border_title = "EStop root cause"
        faultlist.bin_status = 0b0000000001
