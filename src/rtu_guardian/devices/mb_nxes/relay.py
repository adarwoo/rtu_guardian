from textual.widget import Text
from textual.widgets import Button, Label, DataTable, Switch, Rule
from textual.containers import HorizontalGroup, Vertical, VerticalGroup, Horizontal, Grid
from textual.coordinate import Coordinate

from pymodbus.pdu import ModbusPDU

from rtu_guardian.devices.mb_nxes.registers import RelayDiagnosticValues, RelayDiagnostics, Relays, SafetyLogic
from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.modbus.request import ReadCoils, WriteCoils, WriteSingleCoil
from rtu_guardian.devices.utils import modbus_poller

ROWS = [
    "State",
    "Status",
    "Cycles",
    "Filter ON",
    "Filter OFF",
    "Open on infeed fault",
    "Open on comm lost"
]

@modbus_poller(interval=4.2)
class RelayWidget(HorizontalGroup):
    CSS_PATH = "relay.tcss"

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


    def compose(self):
        # Left: Open/Close buttons (vertical)
        with Vertical(id="relay-actions"):
            yield Button("Open", id=f"open_{self.relay_id}")
            yield Button("Close", id=f"close_{self.relay_id}")

        # Add a grid with all infos
        with Vertical(id="relay-info"):
            with Horizontal(classes="centered", id="relay-config-row"):
                yield DataTable(show_header=False, show_cursor=False)
            with Horizontal(classes="centered"):
                yield Button("Configure", id=f"config_{self.relay_id}")

    def on_poll(self):
        """ Request data from the device """
        self.agent.request(
            ReadCoils(self.device_address, self.on_read_coil, address=self.relay_id - 1, count=1)
        )

        self.agent.request(
            RelayDiagnostics.read(
                self.device_address,
                self.on_read_diagnostics,
                f"relay_{self.relay_id}_diag",
                f"relay_{self.relay_id}_cycles"
            )
        )

    def on_read_coil(self, pdu: ModbusPDU):
        """ Process coil status """
        table = self.query_one(DataTable)

        status = "[red]Closed" if pdu.bits[0] else "[green]Open"
        table.update_cell_at(Coordinate(0, 1), status)

    def on_read_diagnostics(self, pdu: dict[str, int]):
        table = self.query_one(DataTable)

        cycles = pdu[f"relay_{self.relay_id}_cycles"]

        try:
            diag = RelayDiagnosticValues(pdu[f"relay_{self.relay_id}_diag"])
            diag = diag.name
        except ValueError:
            diag = "Bad value"

        table.update_cell_at(Coordinate(1, 1), diag)
        table.update_cell_at(Coordinate(2, 1), str(cycles))

    def on_mount(self):
        self.border_title = f"Relay {self.relay_id}"
        table = self.query_one(DataTable)
        table.add_columns("label", " "*8)

        for row in ROWS:
            table.add_row(Text(row, justify="right"), Text("-"))

    def on_show(self):
        self.agent.request(
            Relays.read(
                self.device_address,
                self.on_read_config,
                f"relay_{self.relay_id}_config"
            )
        )

        self.agent.request(
            SafetyLogic.read(
                self.device_address,
                self.on_read_safety_logic,
                SafetyLogic.INFEED_FAULT_RELAY_MASK,
                SafetyLogic.COMM_LOST_RELAY_MASK
            )
        )

    def on_read_config(self, pdu: dict[str, int]):
        table = self.query_one(DataTable)
        raw = pdu[f"relay_{self.relay_id}_config"]

        if raw == 0xFFFF:
            disabled = True
            min_on = 0
            min_off = 0
        else:
            disabled = False
            min_on = (raw >> 8) & 0xFF
            min_off = raw & 0xFF

        table.update_cell_at(Coordinate(3, 1), f"{min_on}.0s")
        table.update_cell_at(Coordinate(4, 1), f"{min_off}.0s")

    def on_read_safety_logic(self, pdu: dict[str, int]):
        table = self.query_one(DataTable)

        infeed_mask = pdu["infeed_fault_relay_mask"]
        comm_mask = pdu["comm_lost_relay_mask"]

        open_on_infeed_faults = (infeed_mask & (1 << (self.relay_id - 1))) != 0
        open_on_comm_lost = (comm_mask & (1 << (self.relay_id - 1))) != 0

        table.update_cell_at(Coordinate(5, 1), "[b]Yes" if open_on_infeed_faults else "No")
        table.update_cell_at(Coordinate(6, 1), "[b]Yes" if open_on_comm_lost else "No")

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == f"open_{self.relay_id}":
            # Open the relay (write coil 0)
            self.agent.request(
                WriteSingleCoil(self.device_address, address=self.relay_id - 1, value=False)
            )
            self.on_poll()
        elif event.button.id == f"close_{self.relay_id}":
            # Close the relay (write coil 1)
            self.agent.request(
                WriteSingleCoil(self.device_address, address=self.relay_id - 1, value=True)
            )
            self.on_poll()



@modbus_poller(interval=0.5)
class RelaysWidget(VerticalGroup):
    def __init__(self, agent: ModbusAgent, device_address: int):
        super().__init__()
        self.agent = agent
        self.device_address = device_address

    def compose(self):
        with Horizontal():
            with Vertical(id="relays-labels"):
                for i in range(3):
                    yield Label(f"Relay {i+1}")

            with Vertical():
                yield Label("[b]Set")
                for i in range(3):
                    yield Switch(value=False, id=f"relay_{i+1}_switch")

                yield Button("Set", id="relay-lr-button")

            yield Rule()

            with Vertical():
                yield Label("[b]Sync")
                for i in range(3):
                    switch = Switch(0, id=f"actual_relay_{i+1}_switch")
                    switch.can_focus = False
                    yield switch

                yield Button("Set", id="relay-lr-button")

            with Horizontal(id="relays-actions"):
                yield Button("Set all", id="relays-set-button")
                yield Button("Clear all", id="relays-clear-button")

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
