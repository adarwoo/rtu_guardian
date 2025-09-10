from textual.screen import ModalScreen
from textual.widgets import Button, LoadingIndicator, Label
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive
from .constants import RECOVERY_ID


INFO = """
[b]To recover a device, follow these steps:[/b]
1. Make sure the device is powered on.
2. Make sure it is properly connected to the RS485.
   In case of doubt, run a scan of the bus and check the device Modbus Rx LED.
   It must show some regular activity. If not, try a different cable or port.
3. Press and hold the EStop button until all LEDs start flashing.
4. Set the device ID and synchronize the communication values.
5. Click [i]'Apply'[/i] to apply the changes to the device and exit this dialog.
"""

class RecoveryDialog(ModalScreen):
    """Dialog to scan for Modbus RTU devices (ID 1 to 247) with ScanMatrix."""
    CSS_PATH = "recovery_dialog.tcss"

    def __init__(self):
        super().__init__()

    def compose(self):
        with Vertical(id="recovery-dialog"):
            yield Label(INFO, id="recovery-info")
            yield LoadingIndicator()
            yield Horizontal(
                Button("Cancel", id="cancel"),
                classes="dialog-buttons"
            )

    async def on_button_pressed(self, event):
        if event.button.id == "cancel":
            self.dismiss()

    def on_mount(self):
        self.query_one("#recovery-dialog").border_title = "Recover your device"
