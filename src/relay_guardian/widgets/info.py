from textual.widgets import DataTable, Button
from textual.containers import HorizontalGroup, Vertical

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

