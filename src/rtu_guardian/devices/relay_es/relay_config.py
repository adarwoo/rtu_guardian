from textual.widgets import Button, Label, Checkbox, Input
from textual.containers import HorizontalGroup, Vertical, Grid, VerticalGroup
from textual.reactive import reactive


class RelayWidget(HorizontalGroup):
    CSS_PATH = "relay.tcss"

    opens_on_feed_fault = reactive(False)
    opens_on_comm_lost = reactive(False)

    def __init__(
        self,
        relay_id: int,
        status: str = "opened",
        cycles: int = 0,
        min_on: float = 0.0,
        min_off: float = 0.0,
        disabled: bool = False,
        infit_faults: bool = False,
        comm_lost: bool = False,
    ):
        super().__init__()
        self.relay_id = relay_id
        self.status = status
        self.cycles = cycles
        self.min_on = min_on
        self.min_off = min_off
        self.disabled = disabled
        self.infit_faults = infit_faults
        self.comm_lost = comm_lost

    def compose(self):
        # Left: Open/Close buttons (vertical)
        with Vertical(classes="relay-actions"):
            yield Button("Open", id=f"open_{self.relay_id}")
            yield Button("Close", id=f"close_{self.relay_id}")

        # Center: Opens On group with checkboxes
        opens_on = VerticalGroup(classes="relay-opens-on")
        opens_on.border_title = "Opens On"
        with opens_on:
            yield Checkbox("in-feed fault", self.opens_on_feed_fault)
            yield Checkbox("comm lost", self.opens_on_comm_lost)

        # Right: Min on/off time edits and disable checkbox
        filter = Grid(classes="relay-filters")
        filter.border_title = "Filters"
        with filter:
            yield Label("Minimum ON time")
            yield Input(type="number", value="0.0")
            yield Label("Minimum OFF time")
            yield Input(type="number", value="0.0")
            yield Checkbox("Disabled", self.disabled)

    def on_mount(self):
        self.border_title = f"Relay {self.relay_id} | {self.status} | Cycles: {self.cycles}"
