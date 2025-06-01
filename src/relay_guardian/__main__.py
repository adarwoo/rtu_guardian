import json
import asyncio

from kivy.app import App

from kivy.clock import Clock
from kivy.properties import (
    StringProperty, BooleanProperty, ListProperty
)
from kivy.logger import Logger
from kivy.lang import Builder
from kivy.metrics import dp  # <-- For dp() in .kv

from pymodbus.client import AsyncModbusSerialClient
from pymodbus.exceptions import ModbusException
from kivy.base import async_runTouchApp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.togglebutton import ToggleButton

CONFIG_FILE = 'config.json'

DEFAULT_CONFIG = {
    "port": "COM1",
    "baudrate": 9600,
    "unit_id": 1,
    "timeout": 1
}

def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        Logger.info(f"Loaded configuration: {config}")
        return config
    except FileNotFoundError:
        Logger.warning(f"Config file '{CONFIG_FILE}' not found. Creating with default values.")
        with open(CONFIG_FILE, 'w') as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        return DEFAULT_CONFIG
    except json.JSONDecodeError:
        Logger.error(f"Error decoding JSON from '{CONFIG_FILE}'. Using default values.")
        return DEFAULT_CONFIG

class ModbusRTUReader:
    def __init__(self, config, update_callback):
        self.config = config
        self.update_callback = update_callback
        self.client = None
        self.register_address = 204
        self.current_value = "N/A"
        self.status_message = "Disconnected"
        self.connection_status = False
        self._running = False

    async def connect(self):
        if self.client and self.client.connected:
            return True

        self.client = AsyncModbusSerialClient(
            port=self.config['port'],
            baudrate=self.config['baudrate'],
            timeout=self.config['timeout'],
            parity=self.config.get('parity', 'N'),
            stopbits=self.config.get('stopbits', 1),
            bytesize=8
        )

        await self.client.connect()

        if self.client.connected:
            self.connection_status = True
            self.status_message = "Connected"
            Logger.info(f"Modbus RTU client connected on {self.config['port']}.")
            return True
        else:
            self.connection_status = False
            self.status_message = f"Connection failed: {self.config['port']}"
            Logger.info(f"Modbus RTU client failed to connect to {self.config['port']}.")
            return False

    async def set_relay_status(self, relay_num, state):
        if not self.connection_status:
            return False

        try:
            response = await self.client.write_coil(relay_num, state, slave=44)

            if response.isError():
                self.status_message = f"Modbus Error: {response}"
                self.current_value = "Error"
            else:
                Logger.info(f"Switched relay: {relay_num} to {'ON' if state else 'OFF'}")
        except Exception as e:
            Logger.error(f"Error whilst switching the relay: {e}")

    async def read_loop(self):
        self._running = True
        while self._running:
            if not self.connection_status:
                await self.connect()

                if not self.connection_status:
                    self.update_callback()
                    await asyncio.sleep(1)
                    continue
            try:
                # Example: Read one coil at register_address
                response = await self.client.read_coils(0, count=3, slave=44)
                if response.isError():
                    self.status_message = f"Modbus Error: {response}"
                    self.current_value = "Error"
                else:
                    value = response.bits[0]
                    self.current_value = str(int(value))
                    self.status_message = "Connected"
            except ModbusException as e:
                self.status_message = f"Modbus Protocol Error: {e}"
                self.current_value = "Error"
                await self.disconnect()
            except Exception as e:
                Logger.error(f"Communication error: {e}")
                self.status_message = f"Communication Error: {e}"
                self.current_value = "Error"
                await self.disconnect()
            self.update_callback()
            await asyncio.sleep(1)

    async def disconnect(self):
        if self.client and self.client.connected:
            await self.client.close()
        self.connection_status = False
        self.status_message = "Disconnected"
        self.current_value = "N/A"

    def stop(self):
        self._running = False


class ModbusReaderApp(App):
    # Status & Diagnostics
    running_time = StringProperty("0")
    relay_cycle = [StringProperty("0"), StringProperty("0"), StringProperty("0")]
    live_voltage = StringProperty("0 V")
    voltage_max = StringProperty("0 V")
    voltage_min = StringProperty("0 V")
    estop_status = StringProperty("OK")
    estop_source = StringProperty("-")
    estop_fault_code = StringProperty("-")
    software_version = StringProperty("-")
    firmware_version = StringProperty("-")
    device_id = StringProperty("1")

    # Control
    relay1_state = StringProperty("off")
    relay2_state = StringProperty("off")
    relay3_state = StringProperty("off")
    relay1_fault = BooleanProperty(False)
    relay2_fault = BooleanProperty(False)
    relay3_fault = BooleanProperty(False)
    estop_context_code = StringProperty("0")

    # Configuration - Communication
    baud_rate = StringProperty("9600")
    stop_bits = StringProperty("1")
    parity = StringProperty("None")

    # Configuration - Infeed
    supply_voltage_type = StringProperty("AC 50Hz")
    low_alarm = StringProperty("0")
    upper_alarm = StringProperty("0")

    # Server Setup
    comm_port = StringProperty("COM1")
    server_baud_rate = StringProperty("9600")
    server_stop_bits = StringProperty("1")
    server_parity = StringProperty("None")
    rts_enabled = BooleanProperty(False)

    # For legacy status
    status_text = StringProperty("Loading...")
    register_value = StringProperty("N/A")

    def build(self):
        self.title = "Modbus RTU Register Reader"
        return Builder.load_file("main.kv")

    def on_start(self):
        self.config = load_config()
        self.modbus_reader = ModbusRTUReader(self.config, self._update_ui_callback)
        self._modbus_task = asyncio.create_task(self.modbus_reader.read_loop())
        # Kivy's tab width adjustment requires to reaval the layout
        Clock.schedule_once(self.root.ids.tp.on_tab_width, 0.1)

    def _update_ui_callback(self):
        Clock.schedule_once(lambda dt: self.update_ui(), 0)

    def update_ui(self, dt=None):
        # Example: update some properties from the Modbus reader
        self.status_text = self.modbus_reader.status_message
        self.register_value = self.modbus_reader.current_value
        # Here you would update all the other properties from your backend logic

    def on_stop(self):
        if hasattr(self, 'modbus_reader'):
            self.modbus_reader.stop()

    # --- Button/Spinner/TextInput handlers (stubs) ---
    def reset_estop(self):
        Logger.info("Reset EStop pressed")

    def reset_infeed_minmax(self):
        Logger.info("Reset In-Feed Min/Max pressed")

    def toggle_locate(self, state):
        Logger.info(f"Locate toggled: {state}")

    def on_relay_set(self, index, state):
        Logger.info(f"Relay {index} toggled: {state}")
        try:
            asyncio.create_task(self.modbus_reader.set_relay_status(index, state))
        except (ValueError, IndexError):
            Logger.error(f"Invalid relay index format: {index}. Expected 'relay_X'.")

    def pulse_estop(self):
        Logger.info("Pulse EStop pressed")

    def terminal_estop(self):
        Logger.info("Terminal EStop pressed")

    def resettable_estop(self):
        Logger.info("Resettable EStop pressed")

    def set_estop_context_code(self, code):
        Logger.info(f"EStop context code set: {code}")
        self.estop_context_code = code

    def set_device_id(self, value):
        Logger.info(f"Device ID set: {value}")
        self.device_id = value

    def set_baud_rate(self, value):
        Logger.info(f"Baud rate set: {value}")
        self.baud_rate = value

    def set_stop_bits(self, value):
        Logger.info(f"Stop bits set: {value}")
        self.stop_bits = value

    def set_parity(self, value):
        Logger.info(f"Parity set: {value}")
        self.parity = value

    def set_supply_voltage_type(self, value):
        Logger.info(f"Supply voltage type set: {value}")
        self.supply_voltage_type = value

    def set_low_alarm(self, value):
        Logger.info(f"Low alarm set: {value}")
        self.low_alarm = value

    def set_upper_alarm(self, value):
        Logger.info(f"Upper alarm set: {value}")
        self.upper_alarm = value

    def set_comm_port(self, value):
        Logger.info(f"Comm port set: {value}")
        self.comm_port = value

    def set_server_baud_rate(self, value):
        Logger.info(f"Server baud rate set: {value}")
        self.server_baud_rate = value

    def set_server_stop_bits(self, value):
        Logger.info(f"Server stop bits set: {value}")
        self.server_stop_bits = value

    def set_server_parity(self, value):
        Logger.info(f"Server parity set: {value}")
        self.server_parity = value

    def set_rts_enabled(self, state):
        Logger.info(f"RTS enabled set: {state}")
        self.rts_enabled = (state == "down")

async def main():
    app = ModbusReaderApp()
    root = app.build()
    app.root = root  # Set the root for Kivy App
    app.dispatch('on_start')  # Manually trigger on_start
    await async_runTouchApp(root)

if __name__ == '__main__':
    asyncio.run(main())