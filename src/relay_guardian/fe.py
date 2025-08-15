from textual.widgets import Header, Footer, TabbedContent, TabPane
from textual.containers import VerticalScroll, HorizontalGroup, Vertical
from textual.app import App
from textual.reactive import reactive
from textual import events

from .config import config

from .widgets.config import ConfigDialog, ConfigDialogClosed
from .widgets.statusbar import StatusBar
from .widgets.relay_device import RelayDeviceWidget


class RelayGuardian(App):
    CSS_PATH = "main.css"

    # Bindings themselves are not reactive, but you can override the watch method
    # to update bindings dynamically. Here's how you can do it:

    BINDINGS = [
        ("q", "quit",     "Quit"),
        ("s", "save",     "Save config"),
        ("S", "scan",     "Scan"),
        ("i", "id",       "Set device ID"),
        ("l", "locate",   "Locate"),
        ("r", "recovery", "Recovery mode"),
        ("c", "config",   "Configuration"),
    ]

    # When this changes, refresh footer/bindings automatically
    can_save = reactive(config.is_changed, bindings=True)
    sub_title = reactive("")

    def __init__(self):
        super().__init__()
        self.status_bar = StatusBar()
        self.header = Header()
        self.update_subtitle()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Check if an action may run."""
        if action == "save":
            return None if not self.can_save else True  # dim/disable when False

        return True

    def update_subtitle(self):
        comport = "COM?" if config['last_com_port'] == "" else f"{config['last_com_port']}"
        self.sub_title = f"{comport} {config['baud']} 8{config['parity']}{config['stop']}"
        self.header.refresh()

    async def on_mount(self):
        self.update_subtitle()
        # If config is default (i.e., just created), prompt user to configure
        if config.is_default:
            await self.push_screen(ConfigDialog())

    def compose(self):
        yield self.header
        yield Footer()

        with TabbedContent(id="any-device-tab-content"):
            for device in [44, 56, 76]:
                yield RelayDeviceWidget(device)

    def action_save(self):
        config.save()
        self.can_save = config.is_changed

    async def action_config(self):
        await self.push_screen(ConfigDialog())

    async def on_config_dialog_closed(self, message: ConfigDialogClosed):
        # Do whatever you need when the dialog closes
        self.refresh()  # or refocus, or update header, etc.
        self.update_subtitle()
