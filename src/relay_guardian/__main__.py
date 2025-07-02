import json
import asyncio
import humanize
import datetime
import struct

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

from .modbus import modbus_operation

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
        self._device_address = self.config['unit_id']

        self.update_callback = update_callback
        self.client = None
        self._running = False

        # Device identification
        self._product_id = None
        self._software_version_value = "-"
        self._hardware_version_value = "-"
        self._number_of_relays = 0

        # Default values for Modbus configuration
        default_relay_config = {"disabled": False, "default_position": False, "inverted": False, "mode_on_fault": "off", "debounce_time": 0}

        # Internal attributes to hold Modbus data, to be updated by read_loop
        self._connection_status = False
        self._status_message = "Disconnected"
        self._current_coil_value = "N/A" # For the single coil read example
        self._coils = [False, False, False] # For relay 0, 1, 2
        self._running_time_value = 0 # Example: holding register for running time
        self._live_voltage_value = 0.0 # Example: holding register for voltage
        self._voltage_max_value = 0.0
        self._voltage_min_value = 0.0
        self._estop_status_value = "OK"
        self._estop_source_value = "-"
        self._estop_fault_code_value = "-"
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
        return self._coils

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
        return self._product_id or "-"

    @property
    def firmware_version_value(self):
        return self._hardware_version_value

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

    async def read_input_registers(self, address, count):
        response = await self.client.read_input_registers(
            slave=self._device_address, address=address, count=count
        )

        if response.isError():
            self._status_message = f"Modbus Error: {response}"
            Logger.error(f"Error whilst reading input registers at {address} [{count}]: {response}")
            return None

        return response.registers

    async def read_holding_registers(self, address, count):
        response = await self.client.read_holding_registers(
            slave=self._device_address, address=address, count=count
        )

        if response.isError():
            self._status_message = f"Modbus Error: {response}"
            Logger.error(f"Error whilst reading holding registers at {address} [{count}]: {response}")
            return None

        return response.registers

    @modbus_operation
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
                if modbus_coil_address < len(self._coils):
                    self._coils[modbus_coil_address] = state
        except Exception as e:
            Logger.error(f"Error whilst switching the relay: {e}")
            self._status_message = f"Relay control error: {e}"
        finally:
            self.update_callback() # Trigger UI update after attempt

    @modbus_operation
    async def read_all_holdings(self):
        # Read input registers 40001 - 40004
        regs = await self.read_holding_registers(0, 24 + self._number_of_relays)

        if regs is not None:
            self._device_address = regs[0]
            self._device_baud_rate = [
                300, 600, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200, 0
            ][max(10, regs[1])]
            self._device_parity = ["None", "Even", "Odd"][regs[2]]
            self._device_stop_bits = 1 if regs[3] == 1 else 2 if regs[3] == 2 else 0

            self._device_infeed_voltage_type = ["AC 50Hz", "AC 60Hz", "DC"][regs[8]]
            self._device_low_alarm = float(regs[9]/10.0)
            self._device_upper_alarm = float(regs[10]/10.0)

            self._estop_on_undervoltage = bool(regs[16] != 0)
            self._estop_on_overvoltage = bool(regs[17] != 0)
            self._estop_on_incorrect_type = bool(regs[18] != 0)
            self._estop_on_modbus_inactivity = regs[19]

            for i in range(self._number_of_relays):
                base = 24 + i
                self._device_relay_config[i]['debounce_time'] = regs[base]
                self._device_relay_config[i]['disabled'] = (regs[base] == 0xFFFF)

    @modbus_operation
    async def read_device_identification(self):
        # Read input registers 30001 - 30004
        regs = await self.read_input_registers(0, 4)

        if regs is not None:
            self._product_id = f"{regs[0]:04x}"
            self._hardware_version_value = regs[1]
            self._software_version_value = regs[2]
            self._number_of_relays = regs[3]

    @modbus_operation
    async def read_status_and_monitoring(self):
        # Read input registers 30009 - 30017
        regs = await self.read_input_registers(8, 9)

        if regs is not None:
            self._current_status = ["operational", "estop", "terminated", "invalid"][min(regs[0], 3)]
            self._running_minutes = regs[1] << 16 | regs[2]
            self._voltage_type = ["none", "dc", "ac", "invalid"][min(regs[3],3)]
            self._infeed_voltage = float(regs[4] / 10.0)
            self._infeed_highest = float(regs[5] / 10.0)
            self._infeed_lowest = float(regs[6] / 10.0)
            self._estop_source_value = [
                "normal", "relay", "modbus",
                "infeed_voltage", "infeed_over", "infeed_under",
                "command", "crash", "invalid"][min(regs[7], 8)]
            self._estop_fault_code_value = regs[8]

    @modbus_operation
    async def read_relays_diag_and_stats(self):
        # Read input registers 30025 - 30033+
        regs = await self.read_input_registers(24, 3 * self._number_of_relays)

        if regs is not None:
            for i in range(self._number_of_relays):
                base = i * 3
                self._relay_diagnostic = ["ok", "faulty", "disabled", "invalid"][min(regs[base], 3)]
                self._relay_cycle_counts = regs[base+1]<<16 | regs[base+2]

    @modbus_operation
    async def read_coils(self):
        coils_response = await self.client.read_coils(
            0,
            slave=self._device_address,
            count=self._number_of_relays,
        )

        if coils_response.isError():
            Logger.error(f"Modbus Error reading coils: {coils_response}")
            self._status_message = f"Modbus Error: {coils_response}"
        else:
            # Update the internal list of coil states
            for i in range(min(len(coils_response.bits), len(self._coils))):
                self._coils[i] = coils_response.bits[i]
            self._status_message = "Connected" # Reset status if successful

    @modbus_operation
    async def set_comm_settings(self, device_address, baud, parity, stops):
        baud_lookup = {
            300:0, 600:1, 1200:2, 2400:3, 4800:4, 9600:5, 19200:6, 38400:7, 57600:8, 115200:9
        }
        parity_lookup = {"none":0, "odd":1, "even":2}
        stop_lookup = { 1:1, 2:2 }
        values = [
            device_address, baud_lookup[baud], parity_lookup[parity], stop_lookup[stops]
        ]

        response = await self.client.write_registers(address=0, values=values, slave=self._device_address)

        # Check the server settings accordingly
        if not response.isError:
            self._device_address = device_address

    @modbus_operation
    async def write_coil(self, index, onoff):
        await self.client.write_coil(index, onoff, slave=self._device_address)

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
        relay_index = 2
        while self._running:
            if not self._connection_status:
                await self.connect()

                if not self._connection_status:
                    self.update_callback()
                    await asyncio.sleep(1)
                    continue
            try:
                if self._product_id is None:
                    await self.read_device_identification()

                await self.read_status_and_monitoring()
                await self.read_relays_diag_and_stats()
                await self.read_coils()
                await self.read_all_holdings()
                await self.write_coil(relay_index, False)
                relay_index = (relay_index + 1) % 3
                await self.write_coil(relay_index, True)

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
        self._coils = [False, False, False]
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
        self.software_version = f"{self.modbus_reader.software_version_value>>8}.{self.modbus_reader.software_version_value&255}"
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

def cb():
    print("SB")

async def main():
    #app = ModbusReaderApp()
    #root = app.build()
    #app.root = root
    #app.dispatch('on_start')
    #await async_runTouchApp(root)
    config = load_config()
    modbus_reader = ModbusRTUReader(config, cb)
    await modbus_reader.read_loop()

if __name__ == '__main__':
    asyncio.run(main())

