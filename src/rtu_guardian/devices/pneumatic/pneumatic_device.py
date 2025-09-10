from textual.containers import Container
from textual.widgets import Static
from textual.reactive import reactive

from rtu_guardian.modbus.agent import ModbusAgent

class PneumaticDevice(Container):
    device_info = reactive("")

    def __init__(self, agent: ModbusAgent, device_address: int):
        super().__init__()
        self.agent = agent
        self.device_address = device_address

    def compose(self):
        yield Static("Work in Progress - Console Device")
