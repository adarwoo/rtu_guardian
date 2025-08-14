from textual.widget import Widget
from textual.reactive import reactive


class StatusBar(Widget):
    # Reactive fields to auto-update on state changes
    connection = reactive("Disconnected")
    status = reactive("Unknown")
    uptime = reactive("0 min")
    voltage = reactive("0.0 V")
    voltage_type = reactive("N/A")
    estop_cause = reactive("None")
    relays = reactive("0 / 0")
    device_id = reactive("0x0000")
    hw_version = reactive("0.0")
    sw_version = reactive("0.0")

    def render(self):
        return f"🔌 {self.connection} | 🟢 {self.status} | ⏱️ {self.uptime} | 🔋 {self.voltage} ({self.voltage_type}) | 🧠 Cause: {self.estop_cause} | 🔧 Relays: {self.relays} | 🆔 ID: {self.device_id} | HW/SW: {self.hw_version} / {self.sw_version}"
