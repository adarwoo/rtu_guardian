import asyncio
from asyncio.log import logger

from pymodbus import FramerType, ModbusException
from pymodbus.client import ModbusSerialClient

from rtu_guardian.config import config
from rtu_guardian.modbus.request import Request, RequestKind


class ModbusAgent:
    def __init__(self, requests):
        self.requests = requests
        self.client: ModbusSerialClient | None = None
        self._app = None
        self._keep_going = True

    def set_app(self, app):
        self._app = app

    def stop(self):
        self._keep_going = False

    @property
    def connected(self):
        return self.client is not None and self.client.connected

    def _open_connection(self):
        """Run the connection attempt in a separate thread."""
        retval = False

        if self.connected:
            self.client.close()

        if config.is_usable:
            try:
                self.client = ModbusSerialClient(
                    port=config['com_port'],
                    baudrate=config['baud'],
                    stopbits=config['stop'],
                    parity=config['parity'],
                    timeout=0.1,
                    framer=FramerType.RTU
                )

                retval = self.client.connect()
                logger.info("Modbus client connected")
            except (ModbusException, ValueError) as e:
                logger.error(f"Error connecting to Modbus client: {e}")

        return retval

    async def run_async(self):
        # Add your main loop or processing logic here
        try:
            while self._keep_going:
                request: Request = await self.requests.get()

                if request.kind == RequestKind.OPEN:
                    self._app.connected = self._open_connection()
        except Exception as e:
            logger.error(f"ModbusAgent encountered an error: {e}")

    def request(self, request: Request):
        self.requests.put_nowait(request)
