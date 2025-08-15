from textual.containers import Container
from textual.widgets import TabbedContent, TabPane
from textual.containers import VerticalGroup

from .infeed import InfeedWidget
from .info import InfoWidget
from .relay import RelayWidget, RelaysWidget
from .estop import EStopWidget


class RelayDeviceWidget(TabPane):
    def __init__(self, id):
        super().__init__(f"Relay #{id}")
        self.idevice_d = id

    def compose(self):
        with TabbedContent():
            with TabPane("Device Information"):
                yield InfoWidget()
            with TabPane("Infeed"):
                yield InfeedWidget()
            with TabPane("All relays"):
                yield RelaysWidget()
            with TabPane("Relay 1"):
                yield RelayWidget(1)
            with TabPane("Relay 2"):
                yield RelayWidget(2)
            with TabPane("Relay 3"):
                yield RelayWidget(3)
            with TabPane("EStop"):
                yield EStopWidget()
