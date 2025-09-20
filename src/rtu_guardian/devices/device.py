import re
import traceback
from enum import Enum, auto
from logging import Logger

from textual.widgets import TabPane, Tab
from textual.containers import Container
from textual.reactive import reactive

from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.modbus.request import ReportDeviceId, ReadDeviceInformation

from ..constants import (
    CSS_KNOWN_DEVICE,
    CSS_UNKNOWN_DEVICE,
    CSS_DISCONNECTED_DEVICE
)

from .scanner import DeviceScanner, DeviceState
from .factory import DeviceFactory, DiscoveredDevice

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
    title = reactive("?")
    status_text = reactive("Scanning for device...")

    def __init__(self, device_address: int, modbus_agent: ModbusAgent):
        super().__init__(f"?@{device_address}", id=f"device-{device_address}")
        self.device_address = device_address
        self.modbus_agent = modbus_agent
        self.scanner = DeviceScanner(modbus_agent, device_address, self)

    def on_mount(self):
        """
        Start scanning
        """
        # Use app to schedule; app reference is available after construction when added to TabbedContent
        self.run_worker(self.scanner.start(), name=f"identify-{self.device_address}")

    def set_title_prefix(self, name: str, class_to_use: str):
        """ Set the title prefix for the device tab """
        tab = self.app.query_one("#devices").query_one(
            f"#--content-tab-device-{self.device_address}", Tab
        )

        tab.reset_styles()
        tab.add_class(class_to_use)
        tab.label = f"{name}@{self.device_address}"

    def on_update_status(self, state: DeviceState, status_text: str, is_final: bool):
        """ Callback from the scanner to update status
            :param state: The current state of the device being scanned
            :param status_text: A human-readable status text
            :param is_final: True if this is the final state (no more updates)
        """
        self.status_text = status_text

        if state == DeviceState.IDENTIFIED:
            self.device_typeid = self.scanner.device_typeid
            self.set_title_prefix(self.device_typeid, CSS_KNOWN_DEVICE)
        elif state == DeviceState.UNKNOWN:
            self.set_title_prefix("unknown", CSS_UNKNOWN_DEVICE)
        elif state == DeviceState.NO_REPLY:
            self.set_title_prefix("away", CSS_DISCONNECTED_DEVICE)
            # Keep trying to identify
            self.run_worker(self.scanner.start(), name=f"identify-{self.device_address}")

    def on_device_identified(self, device: DiscoveredDevice):
        self.status_text = f"Identified device from: {device.type} ({device.module.__name__})"
        self.set_title_prefix(device.type, CSS_KNOWN_DEVICE)
        self.remove_children()
        self.mount(device.widget(self.modbus_agent, self.device_address))

    def render(self):
        # Simple textual status for now
        return self.status_text

