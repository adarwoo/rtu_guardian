from textual.widget import Text
from textual.widgets import DataTable, Button, Input, Rule, Static
from textual.containers import VerticalGroup, HorizontalGroup
from textual.coordinate import Coordinate

from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.devices.utils import modbus_poller

from .registers import (
    DEVICE_CONTROL_ESTOP,
    DEVICE_CONTROL_PULSE,
    DEVICE_CONTROL_RESET,
    DEVICE_CONTROL_TERMINAL,
    DEVICE_ESTOP_CAUSE_RELAY_FAULT,
    DEVICE_ESTOP_CAUSE_MODBUS_COMMLOSS,
    DEVICE_ESTOP_CAUSE_INFEED_POLARITY_INVERSION,
    DEVICE_ESTOP_CAUSE_UNEXPECTED_VOLTAGE_TYPE,
    DEVICE_ESTOP_CAUSE_UNDERVOLTAGE,
    DEVICE_ESTOP_CAUSE_OVERVOLTAGE,
    DEVICE_ESTOP_CAUSE_COMMAND,
    DEVICE_ESTOP_CAUSE_APPLICATION_CRASH,
    DEVICE_ESTOP_CAUSE_EEPROM_CORRUPTED,
    DEVICE_ESTOP_CAUSE_SUPPLY_FAILURE,
    SafetyLogic,
    StatusAndMonitoring,
    DeviceStatus,
    DeviceControl
)

from .static_status_list import StaticStatusList


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

    def compose(self):
        with HorizontalGroup(id="top-section"):
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

        try:
            status = DeviceStatus(pdu["status"]).name
        except ValueError:
            status = f"{pdu['status']}"

        table.update_cell_at(Coordinate(0, 1), status)
        table.update_cell_at(Coordinate(1, 1), pdu["diagnostic_code"])

        # Manage the StaticStatusList
        status_list = self.query_one(StaticStatusList)
        cause = pdu["estop_cause"]

        if cause != 0:
            # Display the StaticStatusList now that we have data
            status_list.visible = True

            # Set the title to indicate the cause is ongoing or historic
            if pdu["status"] == DeviceStatus.ESTOP.value:
                self.border_title = f"[yellow]On-going cause"
            elif pdu["status"] == DeviceStatus.TERMINAL.value:
                self.border_title = f"[red]Terminal cause"
            else:
                self.border_title = f"Uncleared Cause"

            # Update the status list
            status_list.bin_status = cause

    def on_read_safety_logic(self, pdu: dict[str, int]):
        table = self.query_one(DataTable)

        table.update_cell_at(Coordinate(2, 1),
            "[red]Yes" if pdu["estop_on_under_voltage"] else "No")
        table.update_cell_at(Coordinate(3, 1),
            "[red]Yes" if pdu["estop_on_over_voltage"] else "No")
        table.update_cell_at(Coordinate(4, 1),
            "[red]Yes" if pdu["estop_on_incorrect_voltage_type"] else "No")
        table.update_cell_at(Coordinate(5, 1),
            "[red]Yes" if pdu["estop_on_comm_lost"] else "No")

    async def on_button_pressed(self, event):
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

