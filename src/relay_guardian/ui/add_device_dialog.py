from textual.screen import ModalScreen
from textual.widgets import Static, Button, Input, Label
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive


class AddDeviceDialog(ModalScreen):
    """Dialog to scan for Modbus RTU devices (ID 1 to 247) with ScanMatrix."""

    CSS_PATH = "css/add_device_dialog.tcss"

    def __init__(self, active_ids):
        super().__init__()
        self.active_ids = active_ids

    def compose(self):
        with Vertical(id="add-device-dialog") as root:
            with Horizontal(id="add-device-id-group"):
                yield Static("Device ID")
                yield Input(type="integer", placeholder="1-246", id="ext_diag_code")

            yield Label("Some text", id="error-label")

            yield Horizontal(
                Button("Add", id="add"),
                Button("Cancel", id="cancel"),
                classes="dialog-buttons"
            )

        root.border_title = "Add a new device"

    def on_input_changed(self, event: Input.Changed) -> None:
        """Validate input on each keystroke."""
        add_button = self.query_one("#add", Button)
        error_label = self.query_one("#error-label", Label)

        text = event.value.strip()
        valid = False
        message = ""

        if text.isdigit():
            value = int(text)
            if 1 <= value <= 246:
                if value in self.active_ids:
                    message = f"⚠ Device ID {value} already in use!"
                else:
                    valid = True
            else:
                message = "⚠ ID must be between 1 and 246"
        elif text:
            message = "⚠ Must be an integer"

        # Update UI
        add_button.disabled = not valid
        error_label.update(message)
        error_label.styles.color = "red" if message else "green"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss()

        elif event.button.id == "add":
            value = int(self.query_one("#ext_diag_code", Input).value)
            self.dismiss(value)   # return the chosen ID back to caller

    def on_mount(self) -> None:
        # Focus and select the input when the dialog is rendered
        input_widget = self.query_one("#ext_diag_code", Input)
        input_widget.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Treat pressing return as clicking "Add"
        text = event.value.strip()

        if text.isdigit():
            value = int(text)
            if 1 <= value <= 246 and value not in self.active_ids:
                self.dismiss(value)