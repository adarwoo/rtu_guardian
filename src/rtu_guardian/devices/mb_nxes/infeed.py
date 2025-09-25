from textual.widget import Text
from textual.widgets import DataTable, Button
from textual.containers import HorizontalGroup, VerticalGroup
from textual.coordinate import Coordinate

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

        type = InfeedType(pdu["type"]).name
        if type == "BELOW_THRESHOLD":
            type = "Not detected"
        low_threshold = pdu["low_threshold"] / 10.0
        high_threshold = pdu["high_threshold"] / 10.0

        table.update_cell_at(Coordinate(0, 1), f"{type}")
        table.update_cell_at(Coordinate(2, 1), f"{high_threshold}")
        table.update_cell_at(Coordinate(4, 1), f"{low_threshold}")

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

    def on_button_pressed(self, event: Button.Pressed) -> None:
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
            # TODO: Implement configuration dialog
            pass
