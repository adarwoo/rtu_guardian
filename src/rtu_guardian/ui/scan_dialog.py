from enum import Enum, auto

from textual.screen import ModalScreen
from textual.widgets import Label, Button, Static
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive

from rtu_guardian.ui.app import RTUGuardian
from rtu_guardian.device import DeviceScanner, DeviceState
from rtu_guardian.modbus.agent import ModbusAgent

from rtu_guardian.constants import RECOVERY_ID



class ScanState(Enum):
    NOT_SCANNED = auto()
    FOUND = auto()
    PRESUMED = auto()
    CONFIRMED = auto()
    INFIRMED = auto()
    UNKNOWN = auto()
    NOT_FOUND = auto()

LEGEND = """
    Not scanned: [grey39]■[/grey39]
    Presumed   : [orange]✔[/orange]
    Found      : [green]✔[/green]
    Confirmed  : [blue]✔[/blue]
    Infirmined : [red]✖[/red]
    Unknown    : [yellow]?[/yellow]
    No reply   : [gray]·[/gray]
"""

class ScanCell(Static):
    state = reactive(ScanState.NOT_SCANNED)
    """A single cell in the scan matrix representing a Modbus RTU device."""
    DEFAULT_CSS = """
        ScanCell {
            width: 3;
            height: 1;
            padding: 0 0;
            margin-right: 1;
            background: black;
        }
    """

    state = reactive(ScanState.NOT_SCANNED)

    def __init__(self, id_num: int, state: ScanState = ScanState.NOT_SCANNED):
        super().__init__(id=f"scan-cell-{id_num}")
        self.id_num = id_num
        self.state = state

    def render(self):
        if self.id_num == 0 or self.id_num >= RECOVERY_ID:
            return " "

        if self.state == ScanState.FOUND:
            return "[green]✔[/green]"
        elif self.state == ScanState.CONFIRMED:
            return "[blue]✔[/blue]"
        elif self.state == ScanState.INFIRMED:
            return "[red]✖[/red]"
        elif self.state == ScanState.UNKNOWN:
            return "[yellow]?[yellow]"
        elif self.state == ScanState.NOT_FOUND:
            return "[gray]·[/gray]"
        elif self.state == ScanState.PRESUMED:
            return "[orange]✔[/orange]"
        else: # Not scanned
            return "[grey39]■[/grey39]"

    def update(self, state: ScanState):
        if self.id_num > 0 and self.id_num < RECOVERY_ID:
            self.state = state


class ScanMatrix(Vertical):
    def __init__(self, scan_results):
        super().__init__()
        self.rows: list[list[ScanCell]] = []

        for row in range(16):
            row_cells: list[ScanCell] = []

            for col in range(16):
                id_num = row * 16 + col
                state = scan_results.get(id_num, ScanState.NOT_SCANNED)
                cell = ScanCell(id_num, state)
                row_cells.append(cell)

            self.rows.append(row_cells)

    def compose(self):
        # Add a column label for each column
        with Horizontal(classes="scan-header"):
            for col in range(16):
                col_label = Static(f"{col:02X}", classes="col-label")
                yield col_label

        for row_cells in self.rows:
            row_label = Static(f"{row_cells[0].id_num:02X}", classes="row-label")

            with Horizontal():
                yield row_label
                yield from row_cells

    def update_cell(self, id_num: int, state: ScanState):
        row, col = divmod(id_num, 16)
        cell = self.rows[row][col]
        cell.state = state  # This will trigger a redraw of just that cell


class ScanDialog(ModalScreen):
    """Dialog to scan for Modbus RTU devices (ID 1 to 247) with ScanMatrix."""
    CSS_PATH = "css/scan_dialog.tcss"

    def __init__(self):
        super().__init__()
        self.scan_results = {}
        app: RTUGuardian = self.app
        self.active_addresses = app.active_addresses
        self.existing_ids = set()
        self.scanning_address = 1

        for address in self.active_addresses.keys():
            self.scan_results[address] = ScanState.PRESUMED


    def compose(self):
        with Horizontal(id="scan-dialog"):
            yield Label(LEGEND, id="scan-legend")
            with Vertical():
                yield ScanMatrix(self.scan_results)
                yield Horizontal(
                    Button("Close", id="close"),
                    Button("Rescan", id="rescan"),
                    Button("Update", id="update"),
                    classes="dialog-buttons"
                )

    async def on_button_pressed(self, event):
        if event.button.id == "close":
            self.dismiss()
        elif event.button.id == "rescan":
            # You would trigger a rescan here and update scan_results accordingly
            pass

    def on_mount(self):
        self.query_one("#scan-dialog").border_title = "Scan RTU Devices"
        self.query_one("#scan-legend").border_title = "Legend"
        self.query_one("#update").tooltip = """All the devices so far identified, are added"""

        # Start the worker to perform the scan
        self.run_worker(self.perform_scan(), name="scan-devices")

    async def perform_scan(self):
        """Perform the scanning of Modbus RTU devices from ID 1 to 247."""
        app: RTUGuardian = self.app
        modbus_agent: ModbusAgent = app.modbus_agent

        self.scanner = DeviceScanner(
            modbus_agent,
            self.scanning_address,
            self.update_scan_result
        )

        await self.scanner.start()

    def update_scan_result(
        self, state: DeviceState,
        status_text: str,
        is_final: bool
    ):
        """
        Callback from DeviceScanner to update the scan results.
        This is there called from the device scanner thread.
         :param state: The current state of the device being scanned
         :param status_text: A human-readable status text
        """
        app: RTUGuardian = self.app
        scan_matrix: ScanMatrix = self.query_one(ScanMatrix)

        previous_typeid = app.active_addresses.get(self.scanning_address, None)

        if state == DeviceState.IDENTIFIED:
            if previous_typeid is None:
                scan_matrix.update_cell(self.scanning_address, ScanState.FOUND)
            elif previous_typeid != self.scanner.device_typeid:
                scan_matrix.update_cell(self.scanning_address, ScanState.UNKNOWN)
            else:
                scan_matrix.update_cell(self.scanning_address, ScanState.CONFIRMED)
        elif state == DeviceState.UNKNOWN:
            scan_matrix.update_cell(self.scanning_address, ScanState.UNKNOWN)
        elif state == DeviceState.NO_REPLY:
            if previous_typeid is not None:
                scan_matrix.update_cell(self.scanning_address, ScanState.INFIRMED)
            else:
                scan_matrix.update_cell(self.scanning_address, ScanState.NOT_FOUND)

        if is_final:
            self.scanning_address += 1
            if self.scanning_address < RECOVERY_ID:
                self.run_worker(self.perform_scan(), name="scan-devices")
