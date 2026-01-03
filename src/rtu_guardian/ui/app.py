import asyncio
import logging
import sys

from pathlib import Path

from textual.widgets import Header, Footer, TabbedContent, Tab
from textual.app import App
from textual.reactive import reactive

from rtu_guardian.devices.device import Device
from rtu_guardian.config import config

from rtu_guardian.ui.config_dialog import ConfigDialog, ConfigDialogClosed
from rtu_guardian.modbus.agent import ModbusAgent


class TextualLogHandler(logging.Handler):
    def __init__(self, app):
        super().__init__()
        self.app = app

    def emit(self, record):
        msg = self.format(record)
        # Send into Textual log panel
        self.app.log(f"[pymodbus] {msg}")

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running in PyInstaller bundle
        base_path = Path(sys._MEIPASS)
    else:
        # Running in normal Python environment
        base_path = Path(__file__).parent.parent

    return base_path / relative_path

def get_css_path():
    """ Scan the devices subdirectory for all .tcss files and add them to CSS_PATH """
    css_path = []

    # Add main CSS file
    main_css = get_resource_path("rtu_guardian/ui/css/main.tcss")
    if main_css.exists():
        css_path.append(str(main_css))

    # Get devices directory
    devices_dir = get_resource_path("rtu_guardian/devices")

    if devices_dir.exists():
        for subdir in devices_dir.iterdir():
            if subdir.is_dir():
                for file in subdir.glob("*.tcss"):
                    css_path.append(str(file))

    return css_path


class RTUGuardian(App):
    # Scan the devices subdirectory for all .tcss files and add them to CSS_PATH
    CSS_PATH = get_css_path()

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

        self.modbus_agent = ModbusAgent(self.on_connection_status)

        # TabContent that holds all device panes
        self.tab_content = TabbedContent(id="devices")

        # Store worker handle to cancel it when recovery mode is entered or exiting
        self._worker = None

    def on_connection_status(self, status: bool):
        self.connected = status

    # Convenience
    @property
    def active_addresses(self) -> dict[int, str]:
        # Query all tabs in the TabbedContent with id starting with "device-"
        tabs = self.tab_content.query(Tab)
        ids: dict[int, str] = {}
        for tab in tabs:
            try:
                type_id_str, address = tab.label_text.split("@")
                num = int(address)
                ids[num] = type_id_str
            except Exception:
                continue
        return ids

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

        handler = TextualLogHandler(self)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

        pymodbus_logger = logging.getLogger("pymodbus")
        pymodbus_logger.setLevel(logging.DEBUG)
        pymodbus_logger.addHandler(handler)

        device_logger = logging.getLogger("device")
        device_logger.setLevel(logging.DEBUG)
        device_logger.addHandler(handler)

        # If config is default (i.e., just created), prompt user to configure
        if not config.is_usable or config['check_comm']:
            await self.push_screen(ConfigDialog())

        # Start the agent
        self._worker = self.run_worker(
            self.modbus_agent.run_async(), name="modbus_agent"
        )

        # Re-open any previously open devices
        for device_id in config['device_ids']:
            await self.process_add_device(device_id)

    def compose(self):
        yield Header()
        yield Footer()
        yield self.tab_content

    def action_save(self):
        # Update config device_ids
        config.update({"device_ids": list(self.active_addresses.keys())})
        config.save()
        self.can_save = False

    async def action_config(self):
        await self.push_screen(ConfigDialog())

    async def action_recovery(self):
        from rtu_guardian.ui.recovery_dialog import RecoveryScanningDialog

        # Stop the current agent - and close the connection

        if self._worker:
            # Write None to the requests queue to signal the agent to close
            self.modbus_agent.request(None)

            # Wait for worker to finish
            await self._worker.wait()

            # Discard worker handle
            self._worker = None

        # Create a new agent
        await self.push_screen(RecoveryScanningDialog(), callback=self._on_recovery_dialog_closed)

    def _on_recovery_dialog_closed(self, result):
        """Handle recovery dialog result."""

        # Restart the normal agent again
        self._worker = self.run_worker(
            self.modbus_agent.run_async(), name="modbus_agent"
        )

    # Create a new agent
    async def action_add(self):
        from .add_device_dialog import AddDeviceDialog

        dialog = AddDeviceDialog(self.active_addresses)
        await self.push_screen(dialog, self.process_add_device)

    async def action_remove(self):
        # Removes the currently selected device
        if self.tab_content.active:
            self.tab_content.remove_pane(self.tab_content.active)

            # Update config device_ids
            config.update({"device_ids": list(self.active_addresses.keys())})

    async def process_add_device(self, device_id: int):
        """Create and insert a new device tab in numeric order (skip duplicates)."""
        # Create a generic device. The device worker will attempt to identify the actual device
        pane = Device(device_id, self.modbus_agent)

        # Determine pane to insert before (the first existing id greater than new one)
        next_higher = next((i for i in self.active_addresses if i > device_id), None)
        before_pane = self.tab_content.query_one(f"#device-{next_higher}") if next_higher is not None else None
        self.tab_content.add_pane(pane, before=before_pane)

        # Focus added new pane
        self.tab_content.active = pane.id

        # Update config device_ids
        config.update({"device_ids": list(self.active_addresses.keys())})

    async def action_scan(self):
        from .scan_dialog import ScanDialog
        await self.push_screen(ScanDialog())

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
        header.styles.background = "green" if connected else "red"
