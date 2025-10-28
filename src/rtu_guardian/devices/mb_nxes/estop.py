from textual.widget import Text
from textual.widgets import DataTable, Button, Input, Rule, Static, Label
from textual.containers import VerticalGroup, HorizontalGroup, Vertical, Horizontal
from textual.coordinate import Coordinate
from textual.screen import ModalScreen

from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.devices.utils import modbus_poller

from .registers import (
    DEVICE_CONTROL_ESTOP,
    DEVICE_CONTROL_PULSE,
    DEVICE_CONTROL_RESET,
    DEVICE_CONTROL_TERMINAL,
    DEVICE_ESTOP_CAUSE_UNDERVOLTAGE,
    DEVICE_ESTOP_CAUSE_OVERVOLTAGE,
    SafetyLogic,
    StatusAndMonitoring,
    DeviceStatus,
    DeviceControl
)

from .static_status_list import StaticStatusList
from textual.widgets import Checkbox

ROWS = [
    "Status",
    "Diagnostic code",
    "Stop on under voltage",
    "Stop on over voltage",
    "Stop on incorrect voltage type",
    "Stop on comm lost"
]


@modbus_poller(interval=0.3)
class EStopWidget(VerticalGroup):
    def __init__(self, agent: ModbusAgent, device_address: int):
        super().__init__()
        self.agent = agent
        self.device_address = device_address
        self.conf = {
            "under": False,
            "over": False,
            "incorrect": False,
            "comm": 0
        }

    def compose(self):
        with HorizontalGroup(id="top-section"):
            with VerticalGroup():
                yield DataTable(show_header=False, show_cursor=False)

                with HorizontalGroup():
                    yield Button("Clear", id="estop-clear-button")
                    yield Button("Configure>", id="estop-configure-button")

            yield StaticStatusList([
                "Relay fault",
                "Modbus comm loss",
                "Bad Infeed polarity",
                "Bad Infeed Voltage type",
                "Infeed too low",
                "Infeed too high",
                "External EStop",
                "Application crashed",
                "EEProm was recovered",
                "Supply voltage failed",
            ])

        yield Rule(line_style="heavy")

        with HorizontalGroup(id="middle-section"):
            yield Static("Code")
            yield Input(type="integer", placeholder="0-255", id="ext_diag_code")

        with HorizontalGroup(id="bottom-section"):
            yield Button("Pulse", id="estop-pulse-button")
            yield Button("Set", id="estop-set-button")
            yield Button("Terminal", id="estop-terminal-button")

    def on_mount(self):
        self.border_title = "EStop"

        table = self.query_one(DataTable)
        table.add_columns("label", "value..............")
        table.zebra_stripes = True

        for row in ROWS:
            if row.startswith("*"):
                # Highlight measured values
                row = row[1:]
                styled_row = [
                    Text(row, justify="right", style="bold magenta"),
                    Text("-", style="bold magenta")
                ]
            else:
                styled_row = [
                    Text(row, justify="right"),
                    Text("-")
                ]

            table.add_row(*styled_row)

        # Set default value to 0
        input_widget = self.query_one("#ext_diag_code", Input)
        input_widget.value = "0"
        input_widget.tooltip = "Enter an integer 0-255 (decimal or hex)"
        # Trigger validation to set button states
        self.on_input_changed(type("Event", (), {"input": input_widget})())

        # Hide the StaticStatusLists until we have data
        self.query_one(StaticStatusList).visible = False

    def on_poll(self):
        """ Request data from the device """
        self.agent.request(
            SafetyLogic.read(
                self.device_address,
                self.on_read_safety_logic,
                SafetyLogic.ESTOP_ON_UNDER_VOLTAGE,
                SafetyLogic.ESTOP_ON_OVER_VOLTAGE,
                SafetyLogic.ESTOP_ON_INCORRECT_VOLTAGE_TYPE,
                SafetyLogic.ESTOP_ON_COMM_LOST
            )
        )

        self.agent.request(
            StatusAndMonitoring.read(
                self.device_address,
                self.on_read_estop_status,
                StatusAndMonitoring.STATUS,
                StatusAndMonitoring.ESTOP_CAUSE,
                StatusAndMonitoring.DIAGNOSTIC_CODE
            )
        )

    def on_read_estop_status(self, pdu: dict[str, int]):
        table = self.query_one(DataTable)
        status_list = self.query_one(StaticStatusList)

        try:
            status = DeviceStatus(pdu["status"])
            if status == DeviceStatus.OPERATIONAL:
                status = "[green]Operational"
            elif status == DeviceStatus.ESTOP:
                status = "[yellow]E-Stop"
            elif status == DeviceStatus.TERMINAL:
                status = "[red]Terminal"
        except ValueError:
            status = f"{pdu['status']}"

        table.update_cell_at(Coordinate(0, 1), status)

        # Manage the StaticStatusList
        cause = pdu["estop_cause"]
        diag_code = pdu["diagnostic_code"]

        if cause & (DEVICE_ESTOP_CAUSE_UNDERVOLTAGE | DEVICE_ESTOP_CAUSE_OVERVOLTAGE):
            diag_code = str(diag_code) + " (" + str(diag_code / 10.0) + " V)"

        table.update_cell_at(Coordinate(1, 1), diag_code)

        if cause != 0:
            # Display the StaticStatusList now that we have data
            status_list.visible = True

            # Set the title to indicate the cause is ongoing or historic
            if pdu["status"] == DeviceStatus.ESTOP.value:
                status_list.border_title = f"[yellow]On-going cause"
            elif pdu["status"] == DeviceStatus.TERMINAL.value:
                status_list.border_title = f"[red]Terminal cause"
            else:
                status_list.border_title = f"[green]Previous Cause"

            # Update the status list
            status_list.bin_status = cause
        else:
            # No cause active or historic
            status_list.visible = False

    def on_read_safety_logic(self, pdu: dict[str, int]):
        table = self.query_one(DataTable)

        self.conf["under"] = bool(pdu["estop_on_under_voltage"])
        self.conf["over"] = bool(pdu["estop_on_over_voltage"])
        self.conf["incorrect"] = bool(pdu["estop_on_incorrect_voltage_type"])
        self.conf["comm"] = int(pdu["estop_on_comm_lost"])

        table.update_cell_at(Coordinate(2, 1),
            "[red]Yes" if self.conf["under"] else "No")
        table.update_cell_at(Coordinate(3, 1),
            "[red]Yes" if self.conf["over"] else "No")
        table.update_cell_at(Coordinate(4, 1),
            "[red]Yes" if self.conf["incorrect"] else "No")
        table.update_cell_at(Coordinate(5, 1), str(self.conf["comm"]))

    async def on_button_pressed(self, event) -> None:
        button_id = event.button.id

        if button_id in (
            "estop-clear-button",
            "estop-pulse-button",
            "estop-set-button",
            "estop-terminal-button"
        ):
            code = 0

            try:
                code = int(self.query_one("#ext_diag_code", Input).value or 0)
            except ValueError:
                code = 0

            if button_id == "estop-pulse-button":
                value = DEVICE_CONTROL_PULSE | (code & 0xFF)
            elif button_id == "estop-set-button":
                value = DEVICE_CONTROL_ESTOP | (code & 0xFF)
            elif button_id == "estop-terminal-button":
                value = DEVICE_CONTROL_TERMINAL | (code & 0xFF)
            else:  # Clear button
                value = DEVICE_CONTROL_RESET

            self.agent.request(
                DeviceControl.write_single(
                    self.device_address,
                    DeviceControl.SET_RESET_ESTOP,
                    value
                )
            )
        elif button_id == "estop-configure-button":
            # Open the configuration dialog
            dialog = EStopConfigDialog(self.conf.copy())

            try:
                result = await self.app.push_screen_wait(dialog)
                to_change = {}

                if result is not None:
                    if result.get("under") != self.conf["under"]:
                        to_change[SafetyLogic.ESTOP_ON_UNDER_VOLTAGE] = result["under"]
                    if result.get("over") != self.conf["over"]:
                        to_change[SafetyLogic.ESTOP_ON_OVER_VOLTAGE] = result["over"]
                    if result.get("incorrect") != self.conf["incorrect"]:
                        to_change[SafetyLogic.ESTOP_ON_INCORRECT_VOLTAGE_TYPE] = result["incorrect"]
                    if result.get("comm") != self.conf["comm"]:
                        to_change[SafetyLogic.ESTOP_ON_COMM_LOST] = result["comm"]

                    for key, val in to_change.items():
                        self.agent.request(
                            SafetyLogic.write_single(
                                self.device_address,
                                key,
                                int(val)
                            )
                    )
            except Exception as e:
                self.log.error(f"Failed to configure EStop: {e}")

    def on_input_changed(self, event):
        input_widget = event.input
        value = input_widget.value.strip()
        valid = False
        error = False

        if value == "":
            valid = True
            code = 0
        else:
            try:
                # Support hex notation (e.g., 0x1A)
                code = int(value, 0)
                if 0 <= code <= 255:
                    valid = True
                else:
                    error = True
            except ValueError:
                error = True

        # Enable/disable buttons based on validity
        for btn_id in ("estop-pulse-button", "estop-set-button", "estop-terminal-button"):
            btn = self.query_one(f"#{btn_id}", Button)
            btn.disabled = not valid

        # Optionally, flag the input if invalid
        if error:
            input_widget.styles.color = "red"
        else:
            input_widget.styles.color = "green"


class EStopConfigDialog(ModalScreen):
    """Dialog to configure which causes trigger the EStop."""

    def __init__(self, conf: dict):
        super().__init__()
        self.conf = conf

    def compose(self):
        # Checkbox definitions (key, label)
        checkbox_defs = [
            ("under", "Stop on under voltage"),
            ("over", "Stop on over voltage"),
            ("incorrect", "Stop on incorrect voltage type")
        ]

        with Vertical(id="dialog", classes="box"):
            for key, label in checkbox_defs:
                yield Checkbox(label, id=key, value=self.conf.get(key, False))
            with Horizontal():
                yield Label("Stop on comm lost", classes="field_label")
                yield Input(
                    type="integer",
                    placeholder="0-65535",
                    id="comm",
                    value=str(self.conf.get("comm", 0))
                )
            yield Rule(line_style="heavy")
            with HorizontalGroup():
                yield Button("OK", id="ok", variant="success")
                yield Button("Cancel", id="cancel", variant="error")

    def on_mount(self):
        self.query_one("#dialog").border_title = "EStop Configuration"
        # Validate initial state
        self._validate_comm_input()

    def _validate_comm_input(self) -> bool:
        """Validate the comm input and update UI accordingly. Returns True if valid."""
        input_widget = self.query_one("#comm", Input)
        ok_button = self.query_one("#ok", Button)

        value = input_widget.value.strip()
        valid = False

        if value != "":
            try:
                # Support hex notation (e.g., 0x1A) and decimal
                num = int(value, 0)
                if 0 <= num <= 65535:  # 16-bit range
                    valid = True
            except ValueError:
                pass

        # Update input styling
        if valid:
            input_widget.remove_class("invalid")
        else:
            input_widget.add_class("invalid")

        # Enable/disable OK button
        ok_button.disabled = not valid

        return valid

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes in the comm field."""
        if event.input.id == "comm":
            self._validate_comm_input()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        self.conf[event.checkbox.id] = event.value

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok":
            # Get final comm value
            comm_input = self.query_one("#comm", Input)
            try:
                comm_value = int(comm_input.value.strip() or "0", 0)
                self.conf["comm"] = comm_value
            except ValueError:
                # This shouldn't happen due to validation, but just in case
                self.conf["comm"] = 0

            self.dismiss(self.conf)
        else:
            self.dismiss()
