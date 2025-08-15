from textual.screen import ModalScreen
from textual.widgets import Static, Button, Input
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive


class AddDeviceDialog(ModalScreen):
    """Dialog to scan for Modbus RTU devices (ID 1 to 247) with ScanMatrix."""
    CSS_PATH = "add_device_dialog.tcss"

    def __init__(self):
        super().__init__()

    def compose(self):
        with Vertical(id="add-device-dialog"):
            with Horizontal(id="add-device-id-group"):
                yield Static("Device ID")
                yield Input(type="integer", placeholder="1-246", id="ext_diag_code")

            yield Horizontal(
                Button("Add", id="add"),
                Button("Cancel", id="cancel"),
                classes="dialog-buttons"
            )

    async def on_button_pressed(self, event):
        if event.button.id == "cancel":
            self.dismiss()

    def on_mount(self):
        self.query_one("#add-device-dialog").border_title = "Add a new device"
