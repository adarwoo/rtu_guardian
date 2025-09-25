from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message

from textual.widgets import (
    Input,
    Label,
    Checkbox,
    Button,
)


class RelayConfigDialog(ModalScreen):
    """A dialog box for configuring a Modbus relay."""
    def __init__(self, relay_id: int, closed_filter: float = 0.0, opened_filter: float = 0.0, disabled: bool = False):
        super().__init__()
        self.relay_id = relay_id
        self.closed_filter = closed_filter
        self.opened_filter = opened_filter
        self.disabled = disabled
        self._valid_on: bool = False
        self._valid_off: bool = False

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog", classes="box"):
            # Closed filter
            with Horizontal():
                yield Label("Closed Filter (s):", classes="field_label")
                yield Input(
                    placeholder="0.0 - 25.3",
                    id="closed_filter",
                    classes="filter_input"
                )

            # Opened filter
            with Horizontal():
                yield Label("Opened Filter (s):", classes="field_label")
                yield Input(
                    placeholder="0.0 - 25.3",
                    id="opened_filter",
                    classes="filter_input"
                )

            # Disable relay
            with Horizontal():
                yield Label("Disable Relay:", classes="field_label")
                yield Checkbox(id="disable_relay")

            # Action buttons
            with Horizontal(id="dialog-buttons"):
                yield Button("OK", id="ok", variant="success")
                yield Button("Cancel", id="cancel", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok":
            closed_val = self.query_one("#closed_filter", Input).value
            opened_val = self.query_one("#opened_filter", Input).value
            disabled = self.query_one("#disable_relay", Checkbox).value

            # Dismiss with a result payload when OK is pressed
            self.dismiss({
                "disabled": disabled,
                "closed_filter": closed_val,
                "opened_filter": opened_val,
            })
        else:
            # Cancel or other buttons dismiss with None
            self.dismiss(None)

    def on_mount(self) -> None:
        self.query_one("#dialog").border_title = f"Configuration for relay {self.relay_id}"
        self.query_one("#closed_filter").focus()
        self.query_one("#closed_filter", Input).value = str(self.closed_filter)
        self.query_one("#opened_filter", Input).value = str(self.opened_filter)
        self.query_one("#disable_relay", Checkbox).value = self.disabled
        # Validate initial values and set OK state accordingly
        self._validate_all()
        self._apply_disable_state(self.disabled)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Re-validate when user edits either input."""
        if event.input.id in ("closed_filter", "opened_filter"):
            self._validate_all()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "disable_relay":
            self._apply_disable_state(event.value)

    def _apply_disable_state(self, disabled: bool) -> None:
        """Enable/disable inputs and update OK button state accordingly."""
        closed_inp = self.query_one("#closed_filter", Input)
        opened_inp = self.query_one("#opened_filter", Input)
        ok_btn = self.query_one("#ok", Button)

        closed_inp.disabled = disabled
        opened_inp.disabled = disabled

        if disabled:
            # If relay is disabled, allow OK regardless of input validity
            ok_btn.disabled = False
        else:
            # Re-evaluate validity to set OK state
            self._validate_all()

    def _validate_all(self) -> None:
        ok_btn = self.query_one("#ok", Button)
        on_ok = self._validate_one(self.query_one("#closed_filter", Input))
        off_ok = self._validate_one(self.query_one("#opened_filter", Input))
        self._valid_on, self._valid_off = on_ok, off_ok
        ok_btn.disabled = not (on_ok and off_ok)

    @staticmethod
    def _parse_and_check(value_str: str) -> tuple[bool, float | None]:
        """Parse a string to a float and validate 0.0 <= v <= 25.3 with 0.1 step."""
        value_str = value_str.strip()
        if value_str == "":
            return False, None
        try:
            v = float(value_str)
        except ValueError:
            return False, None

        if not (0.0 <= v <= 25.3):
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
