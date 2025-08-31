import asyncio

from textual.widgets import Header, Footer
from textual.app import App
from textual.reactive import reactive

from rtu_guardian.device import DeviceManager
from rtu_guardian.config import config

from rtu_guardian.ui.config_dialog import ConfigDialog, ConfigDialogClosed
from rtu_guardian.modbus.agent import ModbusAgent


class RTUGuardian(App):
    CSS_PATH = "css/main.tcss"

    # Bindings themselves are not reactive, but you can override the watch method
    # to update bindings dynamically. Here's how you can do it:

    BINDINGS = [
        ("q", "quit",     "Quit"),
        ("ctrl+s", "save", "Save config"),
        ("s", "scan",     "Scan"),
        ("r", "recovery", "Recovery mode"),
        ("c", "config",   "Configuration"),
        ("+", "add",      "Add device"),
        ("-", "remove",   "Remove device"),
    ]

    # When this changes, refresh footer/bindings automatically
    can_save = reactive(config.has_unsaved_changes, bindings=True)
    sub_title = reactive("")

    def __init__(self, modbus_agent: ModbusAgent, responses: asyncio.Queue):
        super().__init__()
        self.modbus_agent = modbus_agent
        self.responses = responses

        # The application holds the device manager
        self.device_manager = DeviceManager()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Check if an action may run."""
        if action == "save":
            return None if not self.can_save else True  # dim/disable when False

        return True

    def update_subtitle(self):
        comport = "COM?" if config['last_com_port'] == "" else f"{config['last_com_port']}"

        if modbus_client.is_open:
            self.sub_title = f"{comport} {config['baud']} 8{config['parity']}{config['stop']}"
        else:
            self.sub_title = f"{comport} [red]Disconnected[/red]"

    async def on_mount(self):
        # Start the response consumer worker
        self.run_worker(self.response_consumer())

        self.update_subtitle()

        # If config is default (i.e., just created), prompt user to configure
        if config.is_default:
            await self.push_screen(ConfigDialog())

        modbus_client.notify_config_ready(self)

    def compose(self):
        yield Header()
        yield Footer()

    def action_save(self):
        config.save()
        self.can_save = config.is_changed

    async def action_config(self):
        await self.push_screen(ConfigDialog())

    async def action_recovery(self):
        from ..devices.es_relay.ui.recovery_dialog import RecoveryDialog
        await self.push_screen(RecoveryDialog())

    async def action_add(self):
        from .add_device_dialog import AddDeviceDialog

        dialog = AddDeviceDialog(self.device_manager.active_ids)
        await self.push_screen(dialog, self.process_add_device)

    async def process_add_device(self, device_id: int):
        # Process the addition of a new device
        self.device_manager.attach(device_id)

    async def action_scan(self):
        from .scan_dialog import ScanState, ScanDialog
        scan_results = {
            44: ScanState.FOUND,
            43: ScanState.PRESUMED,
            78: ScanState.NOT_FOUND,
            100: ScanState.UNKNOWN,
            1: ScanState.NOT_FOUND,
            2: ScanState.NOT_FOUND,
            3: ScanState.NOT_FOUND,
            4: ScanState.NOT_FOUND,
            5: ScanState.NOT_FOUND,
            6: ScanState.NOT_FOUND,
            7: ScanState.NOT_FOUND,
            8: ScanState.NOT_FOUND,
            9: ScanState.NOT_FOUND,
            10: ScanState.NOT_FOUND,
            11: ScanState.NOT_FOUND,
            12: ScanState.NOT_FOUND,
            13: ScanState.NOT_FOUND,
            14: ScanState.NOT_FOUND,
            15: ScanState.NOT_FOUND,
            18: ScanState.INFIRMED,
            19: ScanState.CONFIRMED
        }  # {id: ScanState}

        await self.push_screen(ScanDialog(scan_results=scan_results))

    async def on_config_dialog_closed(self, message: ConfigDialogClosed):
        self.refresh()  # or refocus, or update header, etc.
        self.update_subtitle()

    async def on_modbus_status_change(self):
        self.query_one(Header).refresh()
