import json
import asyncio
import functools
import threading

from kivy.logger import Logger

from pymodbus.client import AsyncModbusSerialClient
from pymodbus.exceptions import ModbusException
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian

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

def modbus_operation(func):
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            if not getattr(self, '_connection_status', False):
                Logger.warning("Not connected. Attempting to connect...")
                if not await self.connect():
                    Logger.error("Failed to establish Modbus connection for reading config.")
                    return False
            return await func(self, *args, **kwargs)
        except Exception as e:
            Logger.error(f"Modbus operation '{func.__name__}' failed: {e}")
            return False
    return wrapper


class ModbusRTUReader:
    def __init__(self, update_callback):
        self.input_queue = asyncio.Queue(16)
        self.config = load_config()
        self.client = None
        self.update_callback = update_callback

        self._device_address = self.config['unit_id']

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

        self.thread = threading.Thread(target=self.start_loop)
        self.thread.start()

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
            # Read the device ID upon reconnecting since it could have changed!
            await self.read_device_identification()
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

    def queue_write_coil(self, index, onoff):
        """
        Queue a write_coil operation to be executed by the Modbus loop.
        """
        self.input_queue.put_nowait(('write_coil', (index, onoff), {}))

    async def loop(self):
        """
        Main Modbus loop:
        - Every 1s: read_relays_diag_and_stats
        - Every 200ms: read_coils
        - If input_queue has an operation, execute it immediately (priority)
        """
        last_diag_time = 0
        diag_interval = 1.0
        coil_interval = 0.2

        while True:
            now = asyncio.get_event_loop().time()

            # Priority: handle input requests
            try:
                op = await asyncio.wait_for(self.input_queue.get(), timeout=coil_interval)
                # op should be a tuple: (method_name, args, kwargs)
                method_name, args, kwargs = op
                if method_name == '__stop__':
                    break

                method = getattr(self, method_name)
                await method(*args, **kwargs)
                self.input_queue.task_done()
                continue  # After handling input, skip to next loop
            except TimeoutError:
                # Every 1s: read_relays_diag_and_stats
                if now - last_diag_time >= diag_interval:
                    await self.read_relays_diag_and_stats()
                    last_diag_time = now

            # Every 200ms: read_coils
            await self.read_coils()

    def start_loop(self):
        asyncio.run(self.loop())

    def stop(self):
        """Signal the loop to stop and wait for the thread to finish."""

        # Insert a dummy operation to unblock the queue wait
        try:
            self.input_queue.put_nowait(('__stop__', (), {}))
        except Exception:
            pass

        if hasattr(self, 'thread'):
            self.thread.join(timeout=2)
