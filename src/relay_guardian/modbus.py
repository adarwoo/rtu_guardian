import asyncio
import functools

from kivy.logger import Logger

from pymodbus.client import AsyncModbusSerialClient
from pymodbus.exceptions import ModbusException
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian

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


class RelayModule:
    def __init__(self, port, slave_id=1, baudrate=9600, parity='N', stopbits=1, bytesize=8, timeout=1):
        self.client = AsyncModbusSerialClient(
            method='rtu',
            port=port,
            baudrate=baudrate,
            parity=parity,
            stopbits=stopbits,
            bytesize=bytesize,
            timeout=timeout
        )

        self.unit = slave_id
        self.client.connect()

    def read_coils(self, start=0, count=32):
        """Read relay states (ON/OFF)."""
        rr = self.client.read_coils(start, count, unit=self.unit)
        return rr.bits if rr.isError() is False else None

    def write_single_coil(self, address, state):
        """Write relay ON/OFF (True/False)."""
        return self.client.write_coil(address, state, unit=self.unit)

    def toggle_coil(self, address):
        """Toggle relay using special value 0xAA00."""
        return self.client.write_register(address=address, value=0xAA00, unit=self.unit)

    def write_multiple_coils(self, start, values):
        """Write multiple relays."""
        return self.client.write_coils(start, values, unit=self.unit)

    def read_input_register(self, address, count=1):
        """Read input register(s)."""
        rr = self.client.read_input_registers(address, count, unit=self.unit)
        return rr.registers if rr.isError() is False else None

    def read_holding_register(self, address, count=1):
        """Read holding register(s)."""
        rr = self.client.read_holding_registers(address, count, unit=self.unit)
        return rr.registers if rr.isError() is False else None

    def write_holding_register(self, address, value):
        """Write a single holding register."""
        return self.client.write_register(address, value, unit=self.unit)

    def get_status(self):
        """Return device status: 0=OK, 1=EStop resettable, 2=Terminal EStop."""
        return self.read_input_register(8)[0]

    def get_estop_cause(self):
        """Returns root cause and diagnostic."""
        root_cause = self.read_input_register(13)[0]
        diag_code = self.read_input_register(14)[0]
        return root_cause, diag_code

    def get_voltage_info(self):
        """Returns current, min, max voltage (in 0.1V)."""
        voltage = self.read_input_register(11)[0]
        min_v = self.read_input_register(15)[0]
        max_v = self.read_input_register(16)[0]
        return {
            "current": voltage / 10.0,
            "min": min_v / 10.0,
            "max": max_v / 10.0
        }

    def get_device_info(self):
        """Return product ID, HW/SW version, number of relays."""
        id = self.read_input_register(0)[0]
        hw = self.read_input_register(1)[0]
        sw = self.read_input_register(2)[0]
        relays = self.read_input_register(3)[0]
        return {
            "product_id": hex(id),
            "hw_version": f"{hw & 0xFF}.{hw >> 8}",
            "sw_version": f"{sw & 0xFF}.{sw >> 8}",
            "relays": relays
        }

    def read_relay_diagnostics(self, relay_number):
        """Reads diagnostic for a relay (1-based index)."""
        if not (1 <= relay_number <= 32):
            raise ValueError("Relay index out of range")
        base = 24 + (relay_number - 1) * 3  # 0x18 base + 3 bytes per relay
        diag = self.read_input_register(base)[0]
        cycles = self.read_input_register(base + 1, count=2)
        if cycles:
            cycles_value = (cycles[0] << 16) + cycles[1]
        else:
            cycles_value = None
        return {
            "status": diag,  # 0=OK, 1=Fault, 2=Disabled
            "cycles": cycles_value
        }

    def close(self):
        """Close connection to the relay module."""
        self.client.close()



class ModbusRTUReader:
    def __init__(self, config, update_callback):
        self.config = config
        self.client = None
        self._running = False

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

