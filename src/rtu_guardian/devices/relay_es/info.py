from typing import override

from textual.widgets import DataTable, Switch, Static
from textual.widget import Text
from textual.containers import HorizontalGroup, Vertical, Horizontal
from textual.coordinate import Coordinate

from pymodbus.pdu.mei_message import ReadDeviceInformationResponse

from rtu_guardian.devices.relay_es.registers import DeviceControl, StatusAndMonitoring
from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.modbus.request import ReadDeviceInformation

from rtu_guardian.ui.refreshable import RefreshableWidget

from .static_status_list import StaticStatusList


ROWS = [
    "Vendor name",
    "Product code",
    "Revision",
    "Vendor URL",
    "Model name",
    "Number of relays",
    "Running time"
]

VENDOR_NAME_OBJECT_CODE = 0x00
PRODUCT_CODE_OBJECT_CODE = 0x01
REVISION_OBJECT_CODE = 0x02
VENDOR_URL_OBJECT_CODE = 0x03
PRODUCT_NAME_OBJECT_CODE = 0x04
MODEL_NAME_OBJECT_CODE = 0x05
USER_APPLICATION_NAME_OBJECT_CODE = 0x06
NUMBER_OF_RELAYS_OBJECT_CODE = 0x80


class InfoWidget(HorizontalGroup, RefreshableWidget):
    def __init__(self, agent: ModbusAgent, device_address: int):
        HorizontalGroup.__init__(self)
        RefreshableWidget.__init__(self, agent, device_address, refresh_interval=5.0)

    def compose(self):
        with Vertical():
            yield DataTable(show_header=False, show_cursor=False)
            yield Horizontal(
                Static("Locate: "),
                Switch(id="locate-switch"),
                id="locate-container"
            )

        yield StaticStatusList([
            "Relay fault",
            "Infeed polarity",
            "Voltage type",
            "Low infeed",
            "High infeed",
            "Application crash",
            "EEProm recovered",
            "Supply voltage failure",
        ])

    def on_mount(self):
        self.border_title = f"Device info"

        table = self.query_one(DataTable)
        table.add_columns("label", "value..............")
        table.zebra_stripes = True

        for row in ROWS:
            # Adding styled and justified `Text` objects instead of plain strings.
            styled_row = [
                Text(row, justify="right"),
                Text("-")
            ]

            table.add_row(*styled_row)

        selection = self.query_one(StaticStatusList)
        selection.border_title = "Faults"
        selection.bin_status = 0

        # Request static device information (Requesting is instantaneous)
        self.agent.request(
            ReadDeviceInformation(self.device_address, self.on_device_information, read_code=0x03)
        )

    def on_device_information(self, pdu: ReadDeviceInformationResponse):
        """ Callback from ReadDeviceInformation """
        table = self.query_one(DataTable)

        # Extract values and their corresponding coordinates
        info_map = {
            VENDOR_NAME_OBJECT_CODE:      (0, "Vendor name"),
            PRODUCT_CODE_OBJECT_CODE:     (1, "Product code"),
            REVISION_OBJECT_CODE:         (2, "Revision"),
            VENDOR_URL_OBJECT_CODE:       (3, "Vendor URL"),
            MODEL_NAME_OBJECT_CODE:       (4, "Model name"),
            NUMBER_OF_RELAYS_OBJECT_CODE: (5, "Number of relays"),
        }

        for obj_code, (row_idx, label) in info_map.items():
            value = pdu.information.get(obj_code, b"").decode('ascii').strip()
            table.update_cell_at(Coordinate(row_idx, 1), value)

    @override
    def on_request_data(self):
        """ Override from RefreshableWidget to request dynamic data periodically """
        try:
            # Request the device health and running hours
            self.agent.request(
                StatusAndMonitoring.read(
                    self.device_address,
                    self.on_status_monitoring_reply,
                    StatusAndMonitoring.DEVICE_HEALTH,
                    StatusAndMonitoring.RUNNING_MINUTES
                )
            )
        except Exception as e:
            self.log_error(f"Error requesting data: {e}")

    def on_status_monitoring_reply(self, pdu: dict[str, int]):
        """ Callback from ReadHoldingRegisters for running time """
        table = self.query_one(DataTable)
        status_list = self.query_one(StaticStatusList)

        running_minutes = pdu.get("running_minutes")
        running_hours_str = str(running_minutes // 60)
        running_minutes_str = str(running_minutes % 60)

        table.update_cell_at(Coordinate(6, 1), f"{running_hours_str}'{running_minutes_str}")

        status_list.bin_status = pdu.get("device_health")

    def on_switch_changed(self, event: Switch.Changed):
        """ Called when the locate switch is toggled """
        if event.switch.id == "locate-switch":
            # Turn on locate (write 1 to register 0x20)
            self.agent.request(
                DeviceControl.write_single(
                    self.device_address,
                    DeviceControl.LOCATE,
                    event.value
                )
            )
