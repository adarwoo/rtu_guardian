import asyncio
from textual.widgets import Header, Footer, TabbedContent, TabPane
from textual.app import App
from textual.reactive import reactive
from textual.message import Message

from rtu_guardian.device import Device
from rtu_guardian.config import config

from rtu_guardian.modbus.request import Request
from rtu_guardian.ui.config_dialog import ConfigDialog, ConfigDialogClosed
from rtu_guardian.modbus.agent import ModbusAgent

from rtu_guardian.devices.es_relay.ui.device import Device as ESRelayDevice


class ConnectionStatus(Message):
    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__()


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
    connected = reactive(False)

    def __init__(self):
        super().__init__()

        # Send requests to the agent
        self.requests = asyncio.Queue()

        self.modbus_agent = ModbusAgent(self.requests, self.on_connection_status)

        # TabContent that holds all device panes
        self.tab_content = TabbedContent(id="devices")

    def on_connection_status(self, status: bool):
        self.connected = status

    # Convenience
    @property
    def active_ids(self) -> list[int]:
        # Query all panes with id starting with "device-"
        panes = self.tab_content.query("Device")
        # Extract numeric id from pane id (assumes id="device-<number>")

        ids = []

        for pane in panes:
            try:
                pane_id = getattr(pane, "id", "")
                if pane_id and pane_id.startswith("device-"):
                    num = int(pane_id.split("-", 1)[1])
                    ids.append(num)
            except Exception:
                continue

        return sorted(ids)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Check if an action may run."""
        if action == "save":
            return None if not self.can_save else True  # dim/disable when False

        return True

    async def on_mount(self):
        # Open the connection on startup - unless confirmation is awaiting
        if config['check_comm'] is False:
            # Opening now handled by agent directly when needed.
            pass

        # If config is default (i.e., just created), prompt user to configure
        if not config.is_usable or config['check_comm']:
            await self.push_screen(ConfigDialog())

        # Start the agent
        self.run_worker(
            self.modbus_agent.run_async(), name="modbus_agent"
        )

    async def on_shutdown(self) -> None:
        # Tell the agent to stop gracefully
        self.modbus_agent.stop()

    def compose(self):
        yield Header()
        yield Footer()
        yield self.tab_content

    def action_save(self):
        config.save()
        self.can_save = False

    async def action_config(self):
        await self.push_screen(ConfigDialog())

    async def action_recovery(self):
        from .recovery_dialog import RecoveryDialog
        await self.push_screen(RecoveryDialog())

    async def action_add(self):
        from .add_device_dialog import AddDeviceDialog

        dialog = AddDeviceDialog(self.active_ids)
        await self.push_screen(dialog, self.process_add_device)

    async def action_remove(self):
        # Removes the currently selected device
        if self.tab_content.active:
            self.tab_content.remove_pane(self.tab_content.active)

    async def process_add_device(self, device_id: int):
        """Create and insert a new device tab in numeric order (skip duplicates)."""
        # Create a generic device. The device worker will attempt to identify the actual device
        pane = Device(device_id, self.modbus_agent)

        # Determine pane to insert before (the first existing id greater than new one)
        next_higher = next((i for i in self.active_ids if i > device_id), None)
        before_pane = self.tab_content.query_one(f"#device-{next_higher}") if next_higher is not None else None
        self.tab_content.add_pane(pane, before=before_pane)

        # Optionally focus new pane
        self.tab_content.active = pane.id

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
        if config.is_usable:
            # Opening now handled by agent directly when needed.
            pass

        self.refresh()  # or refocus, or update header, etc.

    async def on_modbus_status_change(self):
        self.query_one(Header).refresh()

    def watch_connected(self, connected: bool):
        comport = "COM?" if config['com_port'] == "" else f"{config['com_port']}"

        self.sub_title = f"{comport} {config['baud']} 8{config['parity']}{config['stop']}"

        header = self.query_one(Header)
        header.styles.background = "green" if self.connected else "red"
