import asyncio
import humanize
import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.properties import (
    StringProperty, BooleanProperty, ListProperty
)
from kivy.logger import Logger
from kivy.lang import Builder
from kivy.metrics import dp

from kivy.base import async_runTouchApp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.togglebutton import ToggleButton


class ModbusReaderApp(App):
    # Status & Diagnostics
    running_time = StringProperty("0 s")
    # Changed relay_cycle to a ListProperty of StringProperty for better binding
    relay_cycle = ListProperty([StringProperty("0"), StringProperty("0"), StringProperty("0")])
    live_voltage = StringProperty("0.0 V")
    voltage_max = StringProperty("0.0 V")
    voltage_min = StringProperty("0.0 V")
    estop_status = StringProperty("Loading...")
    estop_source = StringProperty("-")
    estop_fault_code = StringProperty("-")

    product_id = StringProperty("-")  # Assuming this is a string representation of the product ID
    software_version = StringProperty("-")
    firmware_version = StringProperty("-")

    # Control
    relay_states = ListProperty([False, False, False]) # Boolean states for relays
    relay1_fault = BooleanProperty(False) # Still keep if you have separate fault indicators
    relay2_fault = BooleanProperty(False)
    relay3_fault = BooleanProperty(False)
    estop_context_code = StringProperty("0")

    # Configuration - Communication
    device_id = StringProperty("1")
    baud_rate = StringProperty("9600")
    stop_bits = StringProperty("1")
    parity = StringProperty("N") # Changed default to 'N' for None

    # Configuration - Infeed
    supply_voltage_type = StringProperty("AC 50Hz")
    low_alarm = StringProperty("0")
    upper_alarm = StringProperty("0")

    # Server Setup (assuming these are for a hypothetical Modbus TCP server or similar)
    comm_port = StringProperty("COM1")
    server_baud_rate = StringProperty("9600")
    server_stop_bits = StringProperty("1")
    server_parity = StringProperty("N")
    rts_enabled = BooleanProperty(False)

    # For legacy status
    status_text = StringProperty("Loading...")
    register_value = StringProperty("N/A") # This might be less useful now with specific properties

    def build(self):
        self.title = "Modbus RTU Register Reader"
        return Builder.load_file("main.kv")

    def on_start(self):
        self.config = load_config()
        self.modbus_reader = ModbusRTUReader(self.config, self._update_ui_callback)

        # Initialize Kivy properties from loaded config or defaults
        self.device_id = str(self.config.get('unit_id', DEFAULT_CONFIG['unit_id']))
        self.baud_rate = str(self.config.get('baudrate', DEFAULT_CONFIG['baudrate']))
        self.stop_bits = str(self.config.get('stopbits', DEFAULT_CONFIG['stopbits']))
        self.parity = self.config.get('parity', DEFAULT_CONFIG['parity'])
        self.comm_port = self.config.get('port', DEFAULT_CONFIG['port'])
        self.low_alarm = "10"
        self.upper_alarm = "250"


        # Start the Modbus read loop as an asyncio task
        self._modbus_task = asyncio.create_task(self.modbus_reader.read_loop())
        # Kivy's tab width adjustment requires to reaval the layout
        Clock.schedule_once(self.root.ids.tp.on_tab_width, 0.1)

    def _update_ui_callback(self):
        # Schedule UI updates on the main Kivy thread
        Clock.schedule_once(lambda dt: self.update_ui(), 0)

    def update_ui(self, dt=None):
        # Update status/register from ModbusRTUReader
        self.status_text = self.modbus_reader.status_message
        self.register_value = self.modbus_reader.current_coil_value # Example of a single coil value

        # --- Update Kivy properties from ModbusRTUReader's internal data ---
        delta = datetime.timedelta(minutes=self.modbus_reader.running_time_value)
        self.running_time = humanize.precisedelta(delta, format="%0.0f")
        self.live_voltage = f"{self.modbus_reader.live_voltage_value:.1f} V"
        self.voltage_max = f"{self.modbus_reader.voltage_max_value:.1f} V"
        self.voltage_min = f"{self.modbus_reader.voltage_min_value:.1f} V"
        self.estop_status = self.modbus_reader.estop_status_value
        self.estop_source = self.modbus_reader.estop_source_value
        self.estop_fault_code = self.modbus_reader.estop_fault_code_value
        self.software_version = self.modbus_reader.software_version_value
        self.firmware_version = self.modbus_reader.firmware_version_value
        self.product_id = self.modbus_reader.product_id

        # Update relay cycle counts (convert int to string for StringProperty)
        for i in range(len(self.relay_cycle)):
            if i < len(self.modbus_reader.relay_cycle_counts):
                self.relay_cycle[i] = str(self.modbus_reader.relay_cycle_counts[i])

        # Update the relay toggle button states from Modbus (if read)
        # This is crucial for reflecting actual device state
        for i in range(len(self.relay_states)):
            if i < len(self.modbus_reader.all_coil_states):
                self.relay_states[i] = self.modbus_reader.all_coil_states[i]


    def on_stop(self):
        if hasattr(self, 'modbus_reader'):
            self.modbus_reader.stop()
            if self._modbus_task and not self._modbus_task.done():
                self._modbus_task.cancel()
                Logger.info("Modbus read loop task cancelled.")
            # Ensure disconnect is also awaited or scheduled
            asyncio.create_task(self.modbus_reader.disconnect())
            Logger.info("Modbus client disconnect initiated.")


    # --- Button/Spinner/TextInput handlers (stubs) ---
    def reset_estop(self):
        Logger.info("Reset EStop pressed")
        # Example: write to a Modbus coil/register to reset EStop
        # asyncio.create_task(self.modbus_reader.write_reset_estop_coil(True))

    def reset_infeed_minmax(self):
        Logger.info("Reset In-Feed Min/Max pressed")
        # Example: write to a Modbus coil/register to reset min/max voltage
        # asyncio.create_task(self.modbus_reader.write_reset_voltage_minmax(True))

    def toggle_locate(self, state):
        Logger.info(f"Locate toggled: {state}")
        # Example: write to a Modbus coil for locate function
        # asyncio.create_task(self.modbus_reader.write_locate_coil(state))

    def on_relay_set(self, modbus_coil, state):
        Logger.info(f"Relay coil {modbus_coil} toggled: {state}")
        # Update the Kivy property first to reflect the user's action immediately
        if modbus_coil < len(self.relay_states):
            self.relay_states[modbus_coil] = state
        # Then, schedule the async Modbus call
        asyncio.create_task(self.modbus_reader.set_relay_status(modbus_coil, state))

    def pulse_estop(self):
        Logger.info("Pulse EStop pressed")

    def terminal_estop(self):
        Logger.info("Terminal EStop pressed")

    def resettable_estop(self):
        Logger.info("Resettable EStop pressed")

    def set_estop_context_code(self, code):
        Logger.info(f"EStop context code set: {code}")
        self.estop_context_code = code
        # Example: write to a Modbus register for EStop context code
        # asyncio.create_task(self.modbus_reader.write_estop_context_code(int(code)))

    def set_device_id(self, value):
        Logger.info(f"Device ID set: {value}")
        self.device_id = value # Update Kivy property
        try:
            self.modbus_reader.config['unit_id'] = int(value) # Update Modbus config
            # Reconnect if unit ID changes
            asyncio.create_task(self.modbus_reader.disconnect())
            asyncio.create_task(self.modbus_reader.connect())
        except ValueError:
            Logger.error(f"Invalid Device ID: {value}. Must be an integer.")

    def set_baud_rate(self, value):
        Logger.info(f"Baud rate set: {value}")
        self.baud_rate = value
        try:
            self.modbus_reader.config['baudrate'] = int(value)
            asyncio.create_task(self.modbus_reader.disconnect())
            asyncio.create_task(self.modbus_reader.connect())
        except ValueError:
            Logger.error(f"Invalid Baud Rate: {value}. Must be an integer.")

    def set_stop_bits(self, value):
        Logger.info(f"Stop bits set: {value}")
        self.stop_bits = value
        try:
            self.modbus_reader.config['stopbits'] = int(value)
            asyncio.create_task(self.modbus_reader.disconnect())
            asyncio.create_task(self.modbus_reader.connect())
        except ValueError:
            Logger.error(f"Invalid Stop Bits: {value}. Must be an integer.")

    def set_parity(self, value):
        Logger.info(f"Parity set: {value}")
        self.parity = value
        # Pymodbus expects 'N', 'O', 'E'
        parity_char = value[0] if value != 'None' else 'N'
        self.modbus_reader.config['parity'] = parity_char
        asyncio.create_task(self.modbus_reader.disconnect())
        asyncio.create_task(self.modbus_reader.connect())

    def set_supply_voltage_type(self, value):
        Logger.info(f"Supply voltage type set: {value}")
        self.supply_voltage_type = value
        # Example: Write to a Modbus register for voltage type
        # You'd map 'AC 50Hz', 'AC 60Hz', 'DC' to integer codes for Modbus
        # type_code = 0 if value == 'AC 50Hz' else (1 if value == 'AC 60Hz' else 2)
        # asyncio.create_task(self.modbus_reader.write_voltage_type(type_code))

    def set_low_alarm(self, value):
        Logger.info(f"Low alarm set: {value}")
        self.low_alarm = value
        try:
            # Example: Write to a Modbus register for low alarm threshold
            # asyncio.create_task(self.modbus_reader.write_low_alarm(int(value)))
            pass # Placeholder
        except ValueError:
            Logger.error(f"Invalid Low Alarm: {value}. Must be an integer.")

    def set_upper_alarm(self, value):
        Logger.info(f"Upper alarm set: {value}")
        self.upper_alarm = value
        try:
            # Example: Write to a Modbus register for upper alarm threshold
            # asyncio.create_task(self.modbus_reader.write_upper_alarm(int(value)))
            pass # Placeholder
        except ValueError:
            Logger.error(f"Invalid Upper Alarm: {value}. Must be an integer.")

    def set_comm_port(self, value):
        Logger.info(f"Comm port set: {value}")
        self.comm_port = value
        self.modbus_reader.config['port'] = value
        asyncio.create_task(self.modbus_reader.disconnect())
        asyncio.create_task(self.modbus_reader.connect())

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
