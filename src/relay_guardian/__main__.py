import json
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

from pymodbus.client import AsyncModbusSerialClient
from pymodbus.exceptions import ModbusException
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian

from kivy.base import async_runTouchApp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.togglebutton import ToggleButton

CONFIG_FILE = 'config.json'

DEFAULT_CONFIG = {
    "port": "COM1",
    "baudrate": 9600,
    "stopbits": 1,
    "parity": "N",  # None parity
    "unit_id": 1,
    "timeout": 1,
    "unit_id": 44,  # Default unit ID for Modbus RTU
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
        self._running = False

        # Default values for Modbus configuration
        default_relay_config = {"disabled": False, "default_position": False, "inverted": False, "mode_on_fault": "off", "debounce_time": 0}

        # Internal attributes to hold Modbus data, to be updated by read_loop
        self._connection_status = False
        self._status_message = "Disconnected"
        self._current_coil_value = "N/A" # For the single coil read example
        self._all_coil_states = [False, False, False] # For relay 0, 1, 2
        self._running_time_value = 0 # Example: holding register for running time
        self._live_voltage_value = 0.0 # Example: holding register for voltage
        self._voltage_max_value = 0.0
        self._voltage_min_value = 0.0
        self._estop_status_value = "OK"
        self._estop_source_value = "-"
        self._estop_fault_code_value = "-"
        self._software_version_value = "-"
        self._firmware_version_value = "-"
        self._product_id = "-"
        self._relay_cycle_counts = [0, 0, 0] # Example: holding registers for cycle counts
        self._relay_diagnostic = [0, 0, 0] # Example: holding registers for diagnostic information
        self._device_relay_config = [default_relay_config.copy() for _ in range(3)] # Default relay config for 3 relays

    # Properties to expose internal data for ModbusReaderApp
    @property
    def connection_status(self):
        return self._connection_status

    @property
    def status_message(self):
        return self._status_message

    @property
    def current_coil_value(self):
        return self._current_coil_value

    @property
    def all_coil_states(self):
        return self._all_coil_states

    @property
    def running_time_value(self):
        return self._running_time_value

    @property
    def live_voltage_value(self):
        return self._live_voltage_value

    @property
    def voltage_max_value(self):
        return self._voltage_max_value

    @property
    def voltage_min_value(self):
        return self._voltage_min_value

    @property
    def estop_status_value(self):
        return self._estop_status_value

    @property
    def estop_source_value(self):
        return self._estop_source_value

    @property
    def estop_fault_code_value(self):
        return self._estop_fault_code_value

    @property
    def software_version_value(self):
        return self._software_version_value

    @property
    def product_id(self):
        return self._product_id

    @property
    def firmware_version_value(self):
        return self._firmware_version_value

    @property
    def relay_cycle_counts(self):
        return self._relay_cycle_counts

    async def connect(self):
        if self.client and self.client.connected:
            self._connection_status = True
            self._status_message = "Connected"
            return True

        self.client = AsyncModbusSerialClient(
            port=self.config['port'],
            baudrate=self.config['baudrate'],
            timeout=self.config['timeout'],
            parity=self.config.get('parity', 'N'),
            stopbits=self.config.get('stopbits', 1),
            bytesize=8
        )

        try:
            await self.client.connect()
        except Exception as e:
            Logger.error(f"Failed to connect to Modbus client: {e}")
            self._connection_status = False
            self._status_message = f"Connection failed: {e}"
            self.update_callback() # Trigger UI update on connection failure
            return False

        if self.client.connected:
            self._connection_status = True
            self._status_message = "Connected"
            Logger.info(f"Modbus RTU client connected on {self.config['port']}.")
            self.update_callback() # Trigger UI update on successful connection
            return True
        else:
            self._connection_status = False
            self._status_message = f"Connection failed: {self.config['port']}"
            Logger.info(f"Modbus RTU client failed to connect to {self.config['port']}.")
            self.update_callback() # Trigger UI update on connection failure
            return False

    async def set_relay_status(self, modbus_coil_address, state):
        if not self._connection_status:
            Logger.warning("Not connected to Modbus. Attempting to connect...")
            if not await self.connect():
                Logger.error("Failed to establish Modbus connection for relay control.")
                return False

        try:
            # write_coil expects the coil address (0-indexed) and the boolean state
            response = await self.client.write_coil(modbus_coil_address, state, slave=self.config['unit_id'])

            if response.isError():
                self._status_message = f"Modbus Error: {response}"
                self._current_coil_value = "Error"
                Logger.error(f"Modbus write coil error: {response}")
            else:
                Logger.info(f"Switched relay coil: {modbus_coil_address} to {'ON' if state else 'OFF'}")
                self._status_message = "Relay command sent"
                # Update internal state immediately for faster UI feedback
                if modbus_coil_address < len(self._all_coil_states):
                    self._all_coil_states[modbus_coil_address] = state
        except Exception as e:
            Logger.error(f"Error whilst switching the relay: {e}")
            self._status_message = f"Relay control error: {e}"
        finally:
            self.update_callback() # Trigger UI update after attempt

    async def read_config(self):
        """Read the current Modbus configuration from the device."""
        if not self._connection_status:
            Logger.warning("Not connected to Modbus. Attempting to connect...")
            if not await self.connect():
                Logger.error("Failed to establish Modbus connection for reading config.")
                return False

        try:
            # Example: Read a specific register for configuration
            response = await self.client.read_holding_registers(0, count=10, slave=self.config['unit_id'])

            if response.isError():
                self._status_message = f"Modbus Error: {response}"
                Logger.error(f"Modbus read config error: {response}")
                return False

            # Process the response as needed
            # For example, update internal state or Kivy properties
            Logger.info(f"Configuration read successfully: {response.registers}")
            self._status_message = "Configuration read successfully"

            decoder = BinaryPayloadDecoder.fromRegisters(
                response.registers,
                byteorder=Endian.BIG,
                wordorder=Endian.BIG
            )

            self._device_address = decoder.decode_16bit_uint()
            self._device_baud_rate = [300, 600, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200][decoder.decode_16bit_uint()]  # Example: baud rate
            self._device_parity = ["None", "Even", "Odd"][decoder.decode_8bit_uint()]  # Example: parity
            self._device_stop_bits = decoder.decode_8bit_uint()  # Example: stop bits
            decoder.skip_bytes(4)  # Skip reserved bytes
            self._device_infeed_voltage_type = ["AC 50Hz", "AC 60Hz", "DC"][decoder.decode_8bit_uint()]  # Example: voltage type
            self._device_low_alarm = decoder.decode_16bit_uint()  # Example: low alarm threshold
            self._device_upper_alarm = decoder.decode_16bit_uint()  # Example: upper alarm threshold
            decoder.skip_bytes(10)  # Skip reserved bytes

            for i in range(3):  # Assuming 3 relays
                self._device_relay_config[i]['debounce_time'] = decoder.decode_8bit_uint()
                relay_config = decoder.decode_8bit_uint()
                self._device_relay_config[i]['disabled'] = relay_config & 1
                self._device_relay_config[i]['default_position'] = relay_config & 2
                self._device_relay_config[i]['inverted'] = relay_config & 4
                self._device_relay_config[i]['mode_on_fault'] = ["off", "on"][relay_config & 8]

            return True
        except Exception as e:
            Logger.error(f"Error reading Modbus configuration: {e}")
            self._status_message = f"Config read error: {e}"
            return False

class ModbusRTUReader:
    # Existing code...

    async def trigger_estop(self):
        """Trigger the EStop by writing to the control register at address 40101."""
        if not self._connection_status:
            Logger.warning("Not connected to Modbus. Attempting to connect...")
            if not await self.connect():
                Logger.error("Failed to establish Modbus connection for triggering EStop.")
                return False

        try:
            response = await self.client.write_register(0x0064, 1, slave=self.config['unit_id'])
            if response.isError():
                Logger.error(f"Modbus Error triggering EStop: {response}")
                self._status_message = f"Modbus Error: {response}"
                return False
            Logger.info("EStop triggered successfully.")
            self._status_message = "EStop triggered"
            return True
        except Exception as e:
            Logger.error(f"Error triggering EStop: {e}")
            self._status_message = f"EStop trigger error: {e}"
            return False

    async def write_register(self, address, value, description):
        """Generic method to write to a Modbus register."""
        if not self._connection_status:
            Logger.warning(f"Not connected to Modbus. Attempting to connect for {description}...")
            if not await self.connect():
                Logger.error(f"Failed to establish Modbus connection for {description}.")
                return False

        try:
            response = await self.client.write_register(address, value, slave=self.config['unit_id'])
            if response.isError():
                Logger.error(f"Modbus Error during {description}: {response}")
                self._status_message = f"Modbus Error: {response}"
                return False
            Logger.info(f"{description} successfully.")
            self._status_message = f"{description} completed"
            return True
        except Exception as e:
            Logger.error(f"Error during {description}: {e}")
            self._status_message = f"{description} error: {e}"
            return False

    async def trigger_estop(self):
        """Trigger the EStop."""
        return await self.write_register(0x0064, 1, "Trigger EStop")

    async def reset_measurements(self):
        """Reset measurements."""
        return await self.write_register(0x0065, 0xAA55, "Reset Measurements")

    async def reset_to_factory_defaults(self):
        """Reset configuration to factory defaults and reboot."""
        return await self.write_register(0x0066, 0xAA55, "Reset to Factory Defaults")

    async def reset_device(self):
        """Reset the device."""

    async def read_loop(self):
        self._running = True
        while self._running:
            if not self._connection_status:
                await self.connect()

                if not self._connection_status:
                    self.update_callback()
                    await asyncio.sleep(1)
                    continue
            try:
                # --- Read Coil States for Relays (assuming 3 coils from address 0) ---
                coils_response = await self.client.read_coils(0, count=3, slave=self.config['unit_id'])
                if coils_response.isError():
                    Logger.error(f"Modbus Error reading coils: {coils_response}")
                    self._status_message = f"Modbus Error: {coils_response}"
                else:
                    # Update the internal list of coil states
                    for i in range(min(len(coils_response.bits), len(self._all_coil_states))):
                        self._all_coil_states[i] = coils_response.bits[i]
                    self._status_message = "Connected" # Reset status if successful

                # --- Read Holding Registers (Examples) ---
                # Assuming:
                # Register 100: Running Time (e.g., in seconds)
                # Register 101: Live Voltage (e.g., integer, scale as needed)
                # Register 102: Max Voltage
                # Register 103: Min Voltage
                # Register 104: EStop Status (0=OK, 1=Fault)
                # Register 105: EStop Source (integer code)
                # Register 106: EStop Fault Code (integer code)
                # Register 107: Software Version (e.g., integer for major.minor)
                # Register 108: Firmware Version
                # Registers 110-112: Relay Cycle Counts (for relay 0, 1, 2)

                response = await self.client.read_input_registers(0, count=33, slave=self.config['unit_id'])

                if response.isError():
                    Logger.error(f"Modbus Error reading registers: {response}")
                    self._status_message = f"Modbus Error: {response}"
                else:
                    decoder = BinaryPayloadDecoder.fromRegisters(
                        response.registers,
                        byteorder=Endian.BIG,
                        wordorder=Endian.BIG
                    )

                    self._product_id = f"0x{decoder.decode_16bit_uint():04x}"
                    self._software_version_value = f"v{decoder.decode_8bit_uint()}.{decoder.decode_8bit_uint()}"
                    self._firmware_version_value = f"v{decoder.decode_8bit_uint()}.{decoder.decode_8bit_uint()}"
                    self._number_of_relays = decoder.decode_16bit_uint()  # Example: number of relays
                    decoder.skip_bytes(8)  # Skip reserved bytes
                    self._current_status = decoder.decode_16bit_uint()  # Example: current status code
                    self._running_time_value = decoder.decode_32bit_uint()  # Running time in seconds
                    self._live_voltage_ac = decoder.decode_16bit_uint() * 0.1  # Live voltage
                    self._live_voltage_dc = decoder.decode_16bit_uint() * 0.1  # Live voltage
                    self._estop_root_cause = decoder.decode_16bit_uint()  # EStop root cause
                    self._estop_fault_code_value = decoder.decode_16bit_uint()  # EStop fault code
                    self._infeed_lowest_voltage = decoder.decode_16bit_uint() * 0.1  # Infeed min voltage
                    self._infeed_highest_voltage = decoder.decode_16bit_uint() * 0.1  # Infeed max voltage
                    decoder.skip_bytes(14)  # Skip reserved bytes
                    self._relay_diagnostic[0] = decoder.decode_16bit_uint()  # Relay 0 cycle count
                    self._relay_cycle_counts[0] = decoder.decode_32bit_uint()  # Relay 0 cycle count
                    self._relay_diagnostic[1] = decoder.decode_16bit_uint()  # Relay 0 cycle count
                    self._relay_cycle_counts[1] = decoder.decode_32bit_uint()  # Relay 1 cycle count
                    self._relay_diagnostic[2] = decoder.decode_16bit_uint()  # Relay 0 cycle count
                    self._relay_cycle_counts[2] = decoder.decode_32bit_uint()  # Relay 2 cycle count

                response = await self.client.read_holding_registers(0x10, count=8, slave=self.config['unit_id'])

                if response.isError():
                    Logger.error(f"Modbus Error reading registers: {response}")
                    self._status_message = f"Modbus Error: {response}"
                else:
                    decoder = BinaryPayloadDecoder.fromRegisters(
                        response.registers,
                        byteorder=Endian.BIG,
                        wordorder=Endian.BIG
                    )

                    self._running_time_value = decoder.decode_32bit_uint()
                    self._relay_cycle_counts[0] = decoder.decode_32bit_uint()
                    self._relay_cycle_counts[1] = decoder.decode_32bit_uint()
                    self._relay_cycle_counts[2] = decoder.decode_32bit_uint()

                        #self._live_voltage_value = registers[1] / 10.0 # Register 101, example scaling
                        #self._voltage_max_value = registers[2] / 10.0 # Register 102
                        #self._voltage_min_value = registers[3] / 10.0 # Register 103

                        #estop_status_code = registers[4] # Register 104
                        #self._estop_status_value = "FAULT" if estop_status_code != 0 else "OK"
                        #self._estop_source_value = str(registers[5]) # Register 105
                        #self._estop_fault_code_value = str(registers[6]) # Register 106

                    self._status_message = "Connected" # Reset status if successful

            except ModbusException as e:
                self._status_message = f"Modbus Protocol Error: {e}"
                Logger.error(f"Modbus protocol error in read_loop: {e}")
                await self.disconnect()
            except Exception as e:
                Logger.error(f"Communication error in read_loop: {e}")
                self._status_message = f"Communication Error: {e}"
                await self.disconnect()
            finally:
                self.update_callback() # Always trigger UI update after a read cycle
                await asyncio.sleep(1) # Wait for 1 second before next read

    async def disconnect(self):
        if self.client and self.client.connected:
            await self.client.close()
            Logger.info("Modbus client disconnected.")
        self._connection_status = False
        self._status_message = "Disconnected"
        self._current_coil_value = "N/A" # Reset relevant values on disconnect
        # Reset other values to indicate no data
        self._all_coil_states = [False, False, False]
        self._running_time_value = 0
        self._live_voltage_value = 0.0
        self._voltage_max_value = 0.0
        self._voltage_min_value = 0.0
        self._estop_status_value = "Disconnected" # More specific status
        self._estop_source_value = "-"
        self._estop_fault_code_value = "-"
        self._software_version_value = "-"
        self._firmware_version_value = "-"
        self._relay_cycle_counts = [0, 0, 0]
        self.update_callback() # Trigger UI update after disconnect


    def stop(self):
        self._running = False


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

async def main():
    app = ModbusReaderApp()
    root = app.build()
    app.root = root
    app.dispatch('on_start')
    await async_runTouchApp(root)

if __name__ == '__main__':
    asyncio.run(main())

