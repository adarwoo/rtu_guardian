from textual import on
from textual.widget import Text
from textual.widgets import Button, DataTable
from textual.containers import HorizontalGroup, Vertical, Horizontal
from textual.coordinate import Coordinate
from textual.reactive import reactive

from pymodbus.pdu import ModbusPDU

from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.modbus.request import ReadCoils, WriteSingleCoil
from rtu_guardian.devices.utils import modbus_poller

from .registers import RelayDiagnosticValues, RelayDiagnostics, Relays, SafetyLogic
from .relay_config import RelayConfigDialog

ROWS = [
    "State",
    "Status",
    "Cycles",
    "Closed Minimum Duration",
    "Opened Minimum Duration",
    "Open on infeed fault",
    "Open on comm lost"
]

@modbus_poller(interval=2)
class RelayWidget(HorizontalGroup):
    CSS_PATH = "relay.tcss"

    closed_filter = reactive(0.0)
    opened_filter = reactive(0.0)
    disabled = reactive(False)

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
        self.closed_filter = 0.0
        self.opened_filter = 0.0
        self.disabled = False
        self.open_on_infeed_fault = False
        self.open_on_comm_lost = False
        self.infeed_fault_relay_mask = None
        self.comm_lost_relay_mask = None

    def compose(self):
        # Left: Open/Close buttons (vertical)
        with Vertical(id="relay-actions"):
            yield Button("Open", id=f"open_{self.relay_id}", variant="success")
            yield Button("Close", id=f"close_{self.relay_id}", variant="error")

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

        self.agent.request(SafetyLogic.read(
            self.device_address,
            self.on_read_safety_logic,
            SafetyLogic.INFEED_FAULT_RELAY_MASK,
            SafetyLogic.COMM_LOST_RELAY_MASK,
        ))

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
            self.disabled = True
            self.closed_filter = 0
            self.opened_filter = 0
        else:
            self.disabled = False
            self.closed_filter = ((raw >> 8) & 0xFF) / 10.0
            self.opened_filter = (raw & 0xFF) / 10.0

        table.update_cell_at(Coordinate(3, 1), f"{self.closed_filter}s")
        table.update_cell_at(Coordinate(4, 1), f"{self.opened_filter}s")

    def on_read_safety_logic(self, pdu: dict[str, int]):
        table = self.query_one(DataTable)

        self.infeed_mask = pdu["infeed_fault_relay_mask"]
        self.comm_mask = pdu["comm_lost_relay_mask"]

        mask = 1 << (self.relay_id - 1)
        open_on_infeed_faults = (self.infeed_mask & mask) != 0
        open_on_comm_lost = (self.comm_mask & mask) != 0

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
        elif event.button.id == f"config_{self.relay_id}":
            from rtu_guardian.devices.mb_nxes.relay_config import RelayConfigDialog

            mask = 1 << (self.relay_id - 1)

            dialog = RelayConfigDialog(
                self.relay_id,
                self.closed_filter,
                self.opened_filter,
                self.disabled,
                (self.infeed_mask & mask) != 0,
                (self.comm_mask & mask) != 0
            )

            result = await self.app.push_screen_wait(dialog)

            if result:
                if result["disabled"]:
                    value = 0xFFFF
                    # Update reactive state immediately
                    self.disabled = True
                    self.closed_filter = 0.0
                    self.opened_filter = 0.0
                else:
                    closed_int = int(float(result["closed_filter"]) * 10.0)
                    opened_int = int(float(result["opened_filter"]) * 10.0)

                    value = (closed_int << 8) | opened_int

                    # Update reactive state immediately
                    self.disabled = False
                    self.closed_filter = closed_int / 10.0
                    self.opened_filter = opened_int / 10.0

                    # Write the new configuration (both enabled and disabled cases)
                    self.agent.request(
                        Relays.write_single(
                            self.device_address,
                            f"relay_{self.relay_id}_config",
                            value
                        )
                    )

                    # Apply safety logic changes
                    mask = 1 << (self.relay_id - 1)
                    infeed_mask = self.infeed_mask | mask if result["open_on_infeed_fault"] else self.infeed_mask & ~mask
                    comm_mask = self.comm_mask | mask if result["open_on_comm_lost"] else self.comm_mask & ~mask

                    if infeed_mask != self.infeed_mask:
                        self.agent.request(
                            SafetyLogic.write_single(
                                self.device_address,
                                SafetyLogic.INFEED_FAULT_RELAY_MASK,
                                infeed_mask
                            )
                        )

                    if comm_mask != self.comm_mask:
                        self.agent.request(
                            SafetyLogic.write_single(
                                self.device_address,
                                SafetyLogic.COMM_LOST_RELAY_MASK,
                                comm_mask
                            )
                        )

    def watch_closed_filter(self, value: float) -> None:
        """Update UI when closed_filter changes."""
        try:
            table = self.query_one(DataTable)
            table.update_cell_at(Coordinate(3, 1), f"{value}s")
        except Exception:
            pass

    def watch_opened_filter(self, value: float) -> None:
        """Update UI when opened_filter changes."""
        try:
            table = self.query_one(DataTable)
            table.update_cell_at(Coordinate(4, 1), f"{value}s")
        except Exception:
            pass

    def watch_disabled(self, value: bool) -> None:
        """Update UI when disabled changes (also reflect filters to 0 if disabled)."""
        try:
            table = self.query_one(DataTable)
            # You may also want to style row labels when disabled; here we just ensure filters shown
            if value:
                table.update_cell_at(Coordinate(3, 1), "0s")
                table.update_cell_at(Coordinate(4, 1), "0s")
        except Exception:
            pass


