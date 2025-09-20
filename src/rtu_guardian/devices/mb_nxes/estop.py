from textual.widget import Text
from textual.widgets import DataTable, Button, Input, Rule, Static
from textual.containers import VerticalGroup, HorizontalGroup
from textual.coordinate import Coordinate

from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.devices.utils import modbus_poller

from .registers import SafetyLogic, StatusAndMonitoring, DeviceStatus
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
        self.border_title = f"EStop"
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
