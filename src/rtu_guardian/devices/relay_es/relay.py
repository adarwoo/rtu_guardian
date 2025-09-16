from textual.containers import Container
from textual.widgets import Static, Button, Label, Rule, DataTable, Switch
from textual.containers import HorizontalGroup, Vertical, Grid, VerticalGroup, Horizontal
from textual.reactive import reactive

from pymodbus.pdu import ModbusPDU

from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.modbus.request import ReadCoils, WriteCoils
from rtu_guardian.ui.refreshable import modbus_poller

ROWS = [
    ("Status", "???"),
    ("Cycles", "0"),
    ("Filter ON", "0.0s"),
    ("Filter OFF", "0.0s"),
    ("Open on in-feed fault", "[b]Yes"),
    ("Open on comm lost", "No")
]

class RelayWidget(HorizontalGroup):
    CSS_PATH = "relay.tcss"

    opens_on_feed_fault = reactive(False)
    opens_on_comm_lost = reactive(False)

    def __init__(
        self,
        agent: ModbusAgent,
        device_address: int,
        relay_id: int,
    ):
        super().__init__()
        self.agent = agent
        self.device_address = device_address
        self.relay_id = relay_id

        self.status = "???"
        self.cycles = 0
        self.min_on = 0
        self.min_off = 0
        self.disabled = False
        self.infit_faults = False
        self.comm_lost = False

    def compose(self):
        # Left: Open/Close buttons (vertical)
        with Vertical(classes="relay-actions"):
            yield Button("Open", id=f"open_{self.relay_id}")
            yield Button("Close", id=f"close_{self.relay_id}")

        # Add a grid with all infos
        with Vertical(classes="relay-info"):
            yield DataTable(show_header=False, show_cursor=False)
            yield Button("Configure", id=f"config_{self.relay_id}")

    def on_mount(self):
        self.border_title = f"Relay {self.relay_id}"
        table = self.query_one(DataTable)
        table.add_columns(*ROWS[0])
        table.add_rows(ROWS)


@modbus_poller(interval=0.5)
class RelaysWidget(VerticalGroup):
    relay_status = reactive(0b00000000)

    def __init__(self, agent: ModbusAgent, device_address: int):
        super().__init__()
        self.agent = agent
        self.device_address = device_address

    def compose(self):
        with HorizontalGroup(id="relays-header"):
            with VerticalGroup(id="relays-requested-statuses"):
                yield Label("[b]Requested status", id="requested-status-label")
                for i in range(3):
                    with Horizontal():
                        yield Label(f"Relay {i+1}")
                        yield Switch(value=False, id=f"relay_{i+1}_switch")
                yield Button("Sync", id="relays-sync-button")

            yield Rule(orientation="vertical", line_style="heavy", id="relays-vrule")

            with VerticalGroup(id="relays-actual-statuses"):
                yield Label("Actual status")
                for i in range(3):
                    with Horizontal():
                        switch = Switch(value=self.relay_status & (1 << i) != 0, id=f"actual_relay_{i+1}_switch")
                        switch.can_focus = False
                        yield switch
                yield Button("Set", id="relays-set-button")

    def on_mount(self):
        self.border_title = "Relays position"

    def on_poll(self):
        """ Request data from the device """
        self.agent.request(
            ReadCoils(self.device_address, self.on_read_coil, address=0, count=3)
        )

    def on_read_coil(self, pdu: ModbusPDU):
        """ Process coil status """
        for i in range(3):
            switch = self.query_one(f"#actual_relay_{i+1}_switch", Switch)
            switch.value = pdu.bits[i]

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "relays-sync-button":
            # Collect requested statuses from left switches
            values = []

            for i in range(3):
                switch = self.query_one(f"#relay_{i+1}_switch", Switch)
                values.append( bool(switch.value) )

            # Send the requested status to the relays (example: write coils)
            self.agent.request(
                WriteCoils(self.device_address, address=0, values=values)
            )

            # Read back right after
            self.on_poll()
