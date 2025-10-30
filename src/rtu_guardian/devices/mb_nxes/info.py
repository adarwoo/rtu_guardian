from textual.widgets import DataTable, Switch, Static, Button
from textual.widget import Text
from textual.containers import HorizontalGroup, Vertical, Horizontal
from textual.coordinate import Coordinate

from pymodbus.pdu.mei_message import ReadDeviceInformationResponse

from rtu_guardian.devices.mb_nxes.registers import (
    DEVICE_CONTROL_UNLOCK, DeviceControl, StatusAndMonitoring
)

from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.modbus.request import ReadDeviceInformation

from rtu_guardian.constants import (
    VENDOR_NAME_OBJECT_CODE,
    PRODUCT_CODE_OBJECT_CODE,
    REVISION_OBJECT_CODE,
    VENDOR_URL_OBJECT_CODE,
    MODEL_NAME_OBJECT_CODE,
)


from rtu_guardian.devices.utils import modbus_poller

from .static_status_list import StaticStatusList
from textual.widgets import Button

# Extra MEI Code for the number of relays
NUMBER_OF_RELAYS_OBJECT_CODE = 0x81

ROWS = [
    "Vendor name",
    "Product code",
    "Revision",
    "Vendor URL",
    "Model name",
    "Number of relays",
    "Running time"
]


@modbus_poller(interval=0.5)
class InfoWidget(HorizontalGroup):
    def __init__(self, agent: ModbusAgent, device_address: int):
        HorizontalGroup.__init__(self)
        self.agent = agent
        self.device_address = device_address
        self._awaiting_factory_confirm = 0

    def compose(self):
        with Vertical():
            yield DataTable(show_header=False, show_cursor=False)
            with Horizontal(id="locate-container"):
                yield Static("Locate: ")
                yield Switch(id="locate-switch")
            with Horizontal(id="buttons"):
                yield Button("Reset Device", id="reset", variant="warning")
                yield Button("Factory Reset", id="factory-reset", variant="error")

        yield StaticStatusList([
            "Relay(s) fault",
            None,  # Gap for Bit1
            "Infeed polarity inverted",
            "Infeed incorrect type",
            "Infeed below threshold",
            "Infeed above threshold",
            None, None, # Gaps for Bit6 and Bit7
            "Recovery from crash",
            "EEProm recovered",
            "Power supply fault",
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

    def on_poll(self):
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
            self.log(f"Error requesting data: {e}", level="error")

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

    def on_button_pressed(self, event: Button.Pressed):
        """Handle Reset and Factory Reset button presses.

        - Reset: write the reset register immediately.
        - Factory Reset: require a second confirm press within 5 seconds.
        """
        btn = event.button

        if btn.id == "reset":
            self.agent.request(
                DeviceControl.write_single(
                    self.device_address,
                    DeviceControl.DEVICE_RESET,
                    DEVICE_CONTROL_UNLOCK
                )
            )

            self.log("Requested device reset", level="info")
        elif btn.id == "factory-reset":
            confirm_btn: Button = self.query_one("#factory-reset")

            # Lazily add a confirmation flow: first press asks to confirm,
            # second press within timeout performs the factory reset.
            if self._awaiting_factory_confirm == 0:
                self._awaiting_factory_confirm = 3  # seconds to confirm
                confirm_btn.label = "Confirm (3s)"
                confirm_btn.variant = "warning"

                # Revert confirmation state after 3 seconds
                def _cancel():
                    self._awaiting_factory_confirm -= 1

                    if self._awaiting_factory_confirm > 0:
                        confirm_btn.label = f"Confirm ({self._awaiting_factory_confirm}s)"
                        self.set_timer(1, _cancel)
                        return
                    confirm_btn.label = "Factory Reset"
                    confirm_btn.variant = "error"

                self.set_timer(1, _cancel)

                return

            confirm_btn.label = "Factory Reset"
            confirm_btn.variant = "error"

            # Second press -> perform factory reset
            self.agent.request(
                DeviceControl.write_single(
                    self.device_address,
                    # DeviceControl.RESET_TO_FACTORY_DEFAULTS,
                    DeviceControl.DEVICE_RESET,
                    DEVICE_CONTROL_UNLOCK
                )
            )

            self.log("Requested factory reset", level="warning")
