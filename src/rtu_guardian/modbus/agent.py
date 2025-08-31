from pymodbus import (
    FramerType,
    ModbusException,
)
from pymodbus.client import ModbusSerialClient
from ..config import config
import threading
import time
from textual.message import Message

class ClientConnectionStatus(Message):
    pass


class ModbusAgent:
    def __init__(self):
        self.client = None
        self.is_connected = reactive(False)  # Reactive attribute for GUI to react to
        self.connection_thread = None
        self.stop_thread = False

    def notify_config_ready(self):
        """Notify the client that config is ready and start connection attempt in a thread."""
        if self.connection_thread and self.connection_thread.is_alive():
            self.stop_thread = True
            self.connection_thread.join()

        self.connection_thread = threading.Thread(target=self._open_connection)
        self.connection_thread.start()

    def _open_connection(self):
        """Run the connection attempt in a separate thread."""
        self.stop_thread = False
        while not self.stop_thread:
            try:
                if self.client is not None:
                    self.client.close()

                self.client = ModbusSerialClient(
                    port=config['com_port'],
                    baudrate=config['baud'],
                    stopbits=config['stop'],
                    parity=config['parity'],
                    timeout=1,
                    framer=FramerType.RTU
                )

                self.is_connected = self.client.connect()

                if self.is_connected:
                    # Connection successful, notify GUI via reactive attribute
                    break
                else:
                    raise ModbusException("Failed to connect")
            except ModbusException as e:
                self.is_connected = False
                # Log error or handle as needed
                time.sleep(1)  # Retry after 1 second
            except Exception as e:
                self.is_connected = False
                # Handle other errors
                time.sleep(1)

    def close(self):
        """Close the Modbus client connection."""
        self.stop_thread = True

        if self.connection_thread and self.connection_thread.is_alive():
            self.connection_thread.join()

        if self.client:
            self.client.close()
            self.is_connected = False

# Global instance
modbus_client = ModbusClientWrapper()
