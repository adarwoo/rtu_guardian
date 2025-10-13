from textual.screen import ModalScreen
from textual.widget import Text
from textual.widgets import DataTable, Button
from textual.containers import HorizontalGroup, VerticalGroup
from textual.coordinate import Coordinate
from textual.containers import Horizontal, Vertical
from textual.app import ComposeResult

from textual.widgets import (
    Input,
    Label,
    RadioButton,
    RadioSet,
    Button,
)

from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.devices.utils import modbus_poller

from .registers import (
    DEVICE_CONTROL_UNLOCK,
    InfeedType, PowerInfeed, StatusAndMonitoring, DeviceControl
)

ROWS = [
    "Expected type",
    "*Detected type",
    "Lower voltage threshold",
    "*Lowest measured voltage",
    "Upper voltage threshold",
    "*Highest measured voltage",
    "Current voltage"
]


@modbus_poller(interval=0.5)
class InfeedWidget(VerticalGroup):
    def __init__(self, agent: ModbusAgent, device_address: int):
        super().__init__()
        self.agent = agent
        self.device_address = device_address
        self.infeed_type = InfeedType.BELOW_THRESHOLD
        self.low_threshold = 999.0
        self.high_threshold = 999.0

    def compose(self):
        yield DataTable(show_header=False, show_cursor=False)
        with HorizontalGroup():
            yield Button("Reset", id="infeed-reset-button")
            yield Button("Configure", id="infeed-config-button")

    def on_mount(self):
        self.border_title = f"Infeed"

        table = self.query_one(DataTable)
        table.add_columns("label", " "*16)
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

    async def on_show(self):
        # Request configuration items once per show
        self.agent.request(
            PowerInfeed.read(self.device_address, self.on_read_power_infeed)
        )

    def on_poll(self):
        """ Request data from the device """
        self.agent.request(StatusAndMonitoring.read(
            self.device_address,
            self.on_read_status_and_monitoring,
            StatusAndMonitoring.INFEED_HIGHEST,
            StatusAndMonitoring.INFEED_LOWEST,
            StatusAndMonitoring.INFEED_TYPE,
            StatusAndMonitoring.INFEED_VOLTAGE,
        ))

    def on_read_power_infeed(self, pdu: dict[str, int]):
        """ Process holding registers """
        table = self.query_one(DataTable)

        type = InfeedType(pdu["type"])
        type_str = type.name

        if type == InfeedType.BELOW_THRESHOLD:
            type_str = "Not managed"
        else:
            self.low_threshold = pdu["low_threshold"] / 10.0
            self.high_threshold = pdu["high_threshold"] / 10.0

        table.update_cell_at(Coordinate(0, 1), f"{type}")

        if type == InfeedType.BELOW_THRESHOLD:
            table.update_cell_at(Coordinate(2, 1), "---")
            table.update_cell_at(Coordinate(4, 1), "---")
        else:
            table.update_cell_at(Coordinate(2, 1), f"{self.high_threshold}")
            table.update_cell_at(Coordinate(4, 1), f"{self.low_threshold}")

    def on_read_status_and_monitoring(self, pdu: dict[str, int]):
        """ Process input registers """
        table = self.query_one(DataTable)

        voltage_type = InfeedType(pdu["infeed_type"])

        current_voltage = pdu["infeed_voltage"] / 10.0
        lowest_measured_voltage = pdu["infeed_lowest"] / 10.0
        highest_measured_voltage = pdu["infeed_highest"] / 10.0

        table.update_cell_at(Coordinate(1, 1), f"{voltage_type.name}")
        table.update_cell_at(Coordinate(3, 1), f"{lowest_measured_voltage}")
        table.update_cell_at(Coordinate(5, 1), f"{highest_measured_voltage}")
        table.update_cell_at(Coordinate(6, 1), f"{current_voltage}")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """ Handle button presses """
        button_id = event.button.id

        if button_id == "infeed-reset-button":
            # Reset min/max values
            self.agent.request(
                DeviceControl.write_single(
                    self.device_address,
                    DeviceControl.ZERO_MEASUREMENTS,
                    DEVICE_CONTROL_UNLOCK
                )
            )

        elif button_id == "infeed-config-button":
            # Open configuration dialog (not implemented)
            dialog = InfeedConfigDialog(
                self.infeed_type, self.low_threshold, self.high_threshold
            )

            result = await self.app.push_screen_wait(dialog)

            if result:
                type = InfeedType(result["infeed_type"])
                if type == InfeedType.BELOW_THRESHOLD:
                    low_threshold = 0
                    high_threshold = 2500
                else:
                    low_threshold = int(float(result["low_threshold"]) * 10.0)
                    high_threshold = int(float(result["high_threshold"]) * 10.0)

                    # Write the new configuration (both enabled and disabled cases)
                    self.agent.request(
                        PowerInfeed.write_group(
                            self.device_address,
                            self.infeed_type, low_threshold, high_threshold
                        )
                    )

class InfeedConfigDialog(ModalScreen):
    """Configuration dialog for infeed settings.
    Elements to configure:
        - Infeed type (AC/DC) or None (don't care)
        - Lower voltage threshold (0.0 - 250V)
        - Upper voltage threshold (0.0 - 250V)
    """
    def __init__(self, infeed_type: InfeedType, low_threshold: float, high_threshold: float):
        """Initialize the configuration dialog.

        Args:
            infeed_type (InfeedType): The type of infeed (AC/DC).
            low_threshold (float): The lower voltage threshold (0.0 - 250V) in .1/10V
            high_threshold (float): The upper voltage threshold (0.0 - 250V) in .1/10V
        """
        super().__init__()
        self.infeed_type = infeed_type
        self.low_threshold = low_threshold
        self.high_threshold = high_threshold

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog", classes="box"):
            # Infeed type
            with RadioSet(id="infeed_type"):
                yield RadioButton("any", value=self.infeed_type == InfeedType.BELOW_THRESHOLD)
                yield RadioButton("DC", value=self.infeed_type == InfeedType.DC)
                yield RadioButton("AC", value=self.infeed_type == InfeedType.AC)

            with Horizontal():
                yield Label("Upper voltage threshold (V):", classes="field_label")
                yield Input(
                    placeholder="0.0 - 250.0",
                    id="high_threshold",
                    classes="threshold_input"
                )

            # Low filter
            with Horizontal():
                yield Label("Low voltage threshold (V):", classes="field_label")
                yield Input(
                    placeholder="0.0 - 250.0",
                    id="low_threshold",
                    classes="threshold_input"
                )

            # Action buttons
            with Horizontal(id="dialog-buttons"):
                yield Button("OK", id="ok", variant="success")
                yield Button("Cancel", id="cancel", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok":
            low_val = self.query_one("#low_threshold", Input).value
            high_val = self.query_one("#high_threshold", Input).value

            # Dismiss with a result payload when OK is pressed
            self.dismiss({
                "infeed_type": self.query_one("#infeed_type", RadioSet).pressed_index,
                "low_threshold": low_val,
                "high_threshold": high_val,
            })
        else:
            # Cancel or other buttons dismiss with None
            self.dismiss(None)

    def on_mount(self) -> None:
        self.query_one("#dialog").border_title = f"Infeed configuration"
        self.query_one("#infeed_type").focus()
        self.query_one("#low_threshold", Input).value = str(self.low_threshold)
        self.query_one("#high_threshold", Input).value = str(self.high_threshold)

        # Validate initial values and set OK state accordingly
        self._validate_all()
        self._apply_disable_state(self.disabled)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Re-validate when user edits either input."""
        if event.input.id in ("low_threshold", "high_threshold"):
            self._validate_all()

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if event.radio_set.pressed_index == 0:
            # Disable both thresholds as are no longer applicable
            self._apply_disable_state(event.value)

    def _apply_disable_state(self, disabled: bool) -> None:
        """Enable/disable inputs"""
        low_input = self._validate_one(self.query_one("#low_threshold", Input))
        high_input = self._validate_one(self.query_one("#high_threshold", Input))
        ok_btn = self.query_one("#ok", Button)

        low_input.disabled = disabled
        high_input.disabled = disabled

        if disabled:
            # If relay is disabled, allow OK regardless of input validity
            ok_btn.disabled = False
        else:
            # Re-evaluate validity to set OK state
            self._validate_all()

    def _validate_all(self) -> None:
        ok_btn = self.query_one("#ok", Button)
        self.low_threshold = self._validate_one(self.query_one("#low_threshold", Input))
        self.high_threshold = self._validate_one(self.query_one("#high_threshold", Input))
        ok_btn.disabled = not (self.low_threshold and self.high_threshold)

    @staticmethod
    def _parse_and_check(value_str: str) -> tuple[bool, float | None]:
        """Parse a string to a float and validate 0.0 <= v <= 250 with 0.1 step."""
        value_str = value_str.strip()
        if value_str == "":
            return False, None
        try:
            v = float(value_str)
        except ValueError:
            return False, None

        if not (0.0 <= v <= 250.0):
            return False, None

        # Check 0.1 resolution using integer math with tolerance
        scaled = round(v * 10)
        if abs(v * 10 - scaled) > 1e-9:
            return False, None
        return True, v

    def _validate_one(self, inp: Input) -> bool:
        ok, _ = self._parse_and_check(inp.value)

        # Add/remove 'invalid' class for visual feedback (requires CSS to style if desired)
        if ok:
            inp.remove_class("invalid")
        else:
            inp.add_class("invalid")
        return ok
