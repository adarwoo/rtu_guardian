from textual.screen import ModalScreen
from textual.widgets import Button, Select, Checkbox, Label
from textual.containers import Vertical, VerticalScroll, Horizontal, Grid

from rtu_guardian.config import config, VALID_BAUD_RATES

from textual import work
from textual.reactive import reactive
from textual.timer import Timer
from textual.message import Message

class ConfigDialogClosed(Message):
    """Posted when the ConfigDialog is closed."""
    pass

class ConfigDialog(ModalScreen):
    CSS_PATH = "css/config_dialog.tcss"

    """Dialog for selecting COM port and serial settings."""
    scanning = reactive(True)

    def __init__(self):
        super().__init__()
        self.selected_port = config["com_port"]
        self.selected_baud = str(config["baud"])
        self.selected_stop = str(config["stop"])
        self.selected_parity = config["parity"]
        self._scan_timer: Timer | None = None
        self._ports: list[str] = []

    def compose(self):
        self._ports = config.list_comports()

        if not self._ports:
            vs = Vertical(
                Horizontal(
                    Button("Cancel", id="cancel"),
                    classes="dialog-buttons"
                ),
                classes="config-dialog"
            )
        else:
            buttons = [
                Button("Set and save", id="save"),
                Button("Set", id="ok"),
            ]

            if not config.is_usable:
                buttons.append(Button("Cancel", id="cancel"))

            vs = VerticalScroll(
                Grid(
                    Label("COM Port", classes="dialog-select-label"),
                    Select(
                        [(p, p) for p in self._ports], value=config["com_port"] or self._ports[-1],
                        allow_blank=True,
                        id="com_port",
                        classes="dialog-select"
                    ),
                    Label("Baud Rate", classes="dialog-select-label"),
                    Select(
                        [(str(b), b) for b in VALID_BAUD_RATES],
                        allow_blank=False,
                        value=config["baud"],
                        id="baud", classes="dialog-select"
                    ),
                    Label("Stop Bits", classes="dialog-select-label"),
                    Select(
                        [("1", 1), ("2", 2)],
                        value=config["stop"],
                        allow_blank=False,
                        id="stop",
                        classes="dialog-select"
                    ),
                    Label("Parity", classes="dialog-select-label"),
                    Select(
                        [("None", "N"), ("Even", "E"), ("Odd", "O")],
                        value=config["parity"],
                        allow_blank=False,
                        id="parity",
                        classes="dialog-select"
                    ),
                    id="dialog-select-grid"
                ),

                # Add checkbox for asking on every start
                Horizontal(
                    Checkbox(
                        "Validate COM settings on start",
                        config["check_comm"],
                        id="ask_on_start_checkbox", classes="dialog-checkbox"
                    ),
                    classes="dialog-checkbox-container"
                ),

                Horizontal(
                    *buttons,
                    classes="dialog-buttons"
                ),

                classes="config-dialog"
            )

        vs.border_title = "Configure Serial Port"
        yield vs

    def on_mount(self):
        # Start scanning for ports if none are found
        if not config.list_comports():
            self._scan_timer = self.set_interval(1.0, self._scan_ports, pause=False)

    def on_unmount(self):
        if self._scan_timer:
            self._scan_timer.stop()

    def _scan_ports(self):
        ports = config.list_comports()
        if ports:
            self._scan_timer.stop()
            self.refresh()

    def on_render(self):
        self.query_one("#")

    def on_button_pressed(self, event):
        if event.button.id != "cancel":
            selected_port = self.query_one("#com_port", Select).value
            selected_baud = self.query_one("#baud", Select).value
            selected_stop = self.query_one("#stop", Select).value
            selected_parity = self.query_one("#parity", Select).value
            check_on_startup = self.query_one("#ask_on_start_checkbox").value

            # Update and save global config
            config.update({
                "com_port": selected_port,
                "baud": int(selected_baud),
                "stop": int(selected_stop),
                "parity": selected_parity,
                "check_comm": check_on_startup,
            })

            if event.button.id == "save":
                config.save()

        self.app.post_message(ConfigDialogClosed())
        self.dismiss()
