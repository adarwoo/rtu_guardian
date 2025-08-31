import asyncio
from textual.widgets import TabPane

from rtu_guardian.modbus.proxy import DeviceProxy
from enum import Enum, auto

class DeviceState(Enum):
    SCANNING = auto()
    CONNECTED = auto()
    DISCONNECTED = auto()

class Device:
    def __init__(self, device_id: int):
        self.device_id = device_id
        self.proxy = DeviceProxy(device_id)
        self.tab = TabPane(f"Device {device_id} [yellow]?[yellow]", id=f"device-{device_id}")

        self.state = DeviceState.SCANNING

        # Start a task to scan the device
        self.scan_task = asyncio.create_task(self.scan_device())

    async def scan_device(self):
        while self.state == DeviceState.SCANNING:
            slave_id = await self.proxy.report_slave_id()
            await asyncio.sleep(1)
            # Simulate scanning the device
            # self.proxy.scan()

            self.state = DeviceState.UNKNOWN



class DeviceManager:
    """The device manager brings the UI and modbus together.
    It is responsible for handling all active devices in the system
    Each device added to the UI has a matching proxy object and a UI front.
    The manager is responsible for associating both.
    It is also responsible for adding and removing devices.
    """
    def __init__(self):
        self.devices = {} # ID int -> (DeviceProxy, TabPane)

    def attach(self, device_id: int):
        # Start with creating a place holder
        self.devices[device_id] = Device(device_id)

    def get_device(self, device_id: int):
        return self.devices.get(device_id)

    @property
    def active_ids(self):
        return list(self.devices.keys())
