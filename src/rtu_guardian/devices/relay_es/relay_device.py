from textual.containers import Container
from textual.widgets import TabbedContent, TabPane

from rtu_guardian.modbus.agent import ModbusAgent

from .infeed import InfeedWidget
from .info import InfoWidget
from .relay import RelayWidget, RelaysWidget
from .estop import EStopWidget


class RelayDevice(Container):
    def __init__(self, agent: ModbusAgent, device_address: int):
        super().__init__()
        self.agent = agent
        self.device_address = device_address

    def compose(self):
        with TabbedContent():
            with TabPane("Device Information"):
                yield InfoWidget(self.agent, self.device_address)
            with TabPane("Infeed"):
                yield InfeedWidget(self.agent, self.device_address)
            with TabPane("All relays"):
                yield RelaysWidget(self.agent, self.device_address)
            with TabPane("Relay 1"):
                yield RelayWidget(self.agent, self.device_address, 1)
            with TabPane("Relay 2"):
                yield RelayWidget(self.agent, self.device_address, 2)
            with TabPane("Relay 3"):
                yield RelayWidget(self.agent, self.device_address, 3)
            with TabPane("EStop"):
                yield EStopWidget(self.agent, self.device_address)
