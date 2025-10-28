from logging import Logger

from textual.widgets import TabPane, Tab
from textual.reactive import reactive
from textual.widgets import Button, LoadingIndicator, Label, TabbedContent
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive

from rtu_guardian.modbus.agent import ModbusAgent

from ..constants import (
    CSS_KNOWN_DEVICE,
    CSS_UNKNOWN_DEVICE,
    CSS_DISCONNECTED_DEVICE
)

from .scanner import DeviceScanner, DeviceState
from .factory import DiscoveredDevice

logger = Logger("device")


class Device(TabPane):
    """
    The device is the TabPane which owns a given device.
    The content area defaults to the device's status text until the device
    type is established - then the content becomes substituted with the correct
    type.
    The Device handles all outgoing communication with the device, through the
    agent.
    """
    status_text = reactive("Scanning for device...")
    device_state = reactive(DeviceState.QUERYING)

    def __init__(self, device_address: int, modbus_agent: ModbusAgent):
        super().__init__(f"?@{device_address}", id=f"device-{device_address}")

        self.device_address = device_address
        self.modbus_agent = modbus_agent

        self.scanner = DeviceScanner(modbus_agent, device_address, self)

    def compose(self):
        with Vertical(classes="scanning-device-border"):
            yield LoadingIndicator()

    def on_mount(self):
        border = self.query_one(".scanning-device-border")
        border.border_title = f"Searching device @{self.device_address}"
        self.run_worker(self.scanner.start(), name=f"identify-{self.device_address}")

    def set_title_prefix(self, name: str, class_to_use: str | None) -> None:
        """ Set the title prefix for the device tab """
        # More robust tab finding
        tabbed_content: TabbedContent = self.app.query_one("#devices")
        tab: Tab = tabbed_content.get_tab(f"device-{self.device_address}")
        tab.set_class(class_to_use==CSS_KNOWN_DEVICE, CSS_KNOWN_DEVICE)
        tab.set_class(class_to_use==CSS_UNKNOWN_DEVICE, CSS_UNKNOWN_DEVICE)
        tab.set_class(class_to_use==CSS_DISCONNECTED_DEVICE, CSS_DISCONNECTED_DEVICE)

        tab.label = f"{name}@{self.device_address}"

    def watch_status_text(self, new_text: str) -> None:
        """Watch for changes to the status text"""
        border = self.query_one(".scanning-device-border")
        border.border_title = f"{new_text}@{self.device_address}"

    def watch_device_state(self, new_state: DeviceState) -> None:
        """React to device state changes and update tab styling accordingly"""
        css_class = None

        if new_state == DeviceState.IDENTIFIED:
            css_class = CSS_KNOWN_DEVICE
            title_prefix = self.device_typeid if hasattr(self, 'device_typeid') else "identified"
        elif new_state == DeviceState.UNKNOWN:
            css_class = CSS_UNKNOWN_DEVICE
            title_prefix = "unknown"
        elif new_state == DeviceState.NO_REPLY:
            css_class = CSS_DISCONNECTED_DEVICE
            title_prefix = "no reply"
        else:  # SCANNING
            title_prefix = "scanning"

        # Update title without losing focus
        self.title = f"{title_prefix}@{self.device_address}"

        # Update tab styling
        self.set_title_prefix(title_prefix, css_class)

    def on_update_status(self, state: DeviceState, status_text: str, is_final: bool):
        """ Callback from the scanner to update status
        When final, the tab may want to re-run the scanner if no reply
        :param state: The new device state
        :param status_text: The status text to display
        :param is_final: Whether this is a final state
        """
        self.status_text = status_text
        self.device_state = state  # This will trigger watch_device_state

        if state == DeviceState.IDENTIFIED:
            self.device_typeid = self.scanner.device_typeid
        elif state == DeviceState.NO_REPLY and is_final:
            # Keep trying to identify only if not final
            self.run_worker(self.scanner.start(), name=f"identify-{self.device_address}")

    def on_device_identified(self, device: DiscoveredDevice):
        self.status_text = f"Identified device from: {device.type} ({device.module.__name__})"
        self.set_title_prefix(device.type, CSS_KNOWN_DEVICE)
        self.remove_children()
        self.mount(device.widget(self.modbus_agent, self.device_address))
