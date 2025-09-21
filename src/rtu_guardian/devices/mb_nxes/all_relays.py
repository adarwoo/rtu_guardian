from textual.widgets import Button, Label, Switch, Rule
from textual.containers import Vertical, VerticalGroup, Horizontal

from pymodbus.pdu import ModbusPDU

from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.modbus.request import ReadCoils, WriteCoils
from rtu_guardian.devices.utils import modbus_poller


@modbus_poller(interval=0.5)
class RelaysWidget(VerticalGroup):
    def __init__(self, agent: ModbusAgent, device_address: int):
        super().__init__()
        self.agent = agent
        self.device_address = device_address

    def compose(self):
        with Horizontal(id="relay-individuals"):
            with Vertical(id="relays-labels"):
                for i in range(3):
                    yield Label(f"Relay {i+1}")

            with Vertical(id="relays-set"):
                yield Label("[b]Set")
                for i in range(3):
                    yield Switch(value=False, id=f"relay_{i+1}_switch")

                yield Button("Set >", id="relay-set", classes="centered-button")

            yield Rule("vertical")

            with Vertical(id="relays-sync"):
                yield Label("[b]Sync")
                for i in range(3):
                    switch = Switch(0, id=f"actual_relay_{i+1}_switch")
                    switch.can_focus = False
                    yield switch

                yield Button("< Sync", id="relay-sync", classes="centered-button")

        with Horizontal(id="relays-actions"):
            yield Button("Set all", id="relays-set")
            yield Button("Clear all", id="relays-clear")

    def on_mount(self):
        self.border_title = "Relays position"

    def on_poll(self):
        """ Request data from the device """
        self.agent.request(
            ReadCoils(self.device_address, self.on_read_coil, address=0, count=3)
        )

    def on_read_coil(self, pdu: ModbusPDU):
        """ Process coil status """
        for i in range(3):
            switch = self.query_one(f"#actual_relay_{i+1}_switch", Switch)
            switch.value = pdu.bits[i]

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "relay-set":
            # Collect requested statuses from left switches
            values = []

            for i in range(3):
                switch = self.query_one(f"#relay_{i+1}_switch", Switch)
                values.append( bool(switch.value) )

            # Send the requested status to the relays (example: write coils)
            self.agent.request(
                WriteCoils(self.device_address, address=0, values=values)
            )
        elif event.button.id == "relay-sync":
            # Collect requested statuses from right switches
            for i in range(3):
                switch_from = self.query_one(f"#actual_relay_{i+1}_switch", Switch)
                switch_to = self.query_one(f"#relay_{i+1}_switch", Switch)
                switch_to.value = switch_from.value
        elif event.button.id == "relays-set":
            # Send the requested status to the relays (example: write coils)
            self.agent.request(
                WriteCoils(self.device_address, address=0, values=[True, True, True])
            )
        elif event.button.id == "relays-clear":
            # Send the requested status to the relays (example: write coils)
            self.agent.request(
                WriteCoils(self.device_address, address=0, values=[False, False, False])
            )

        # Read back right after
        self.on_poll()
