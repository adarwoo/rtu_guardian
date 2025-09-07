import asyncio
from asyncio.log import logger

from pymodbus import FramerType, ModbusException
from pymodbus.client import AsyncModbusSerialClient

from rtu_guardian.config import config
from rtu_guardian.modbus.request import Request


class ModbusAgent:
    def __init__(self, requests: asyncio.Queue[Request], on_connection_status: callable):
        self.requests = requests
        self.client: AsyncModbusSerialClient | None = None
        self._app = None
        self._keep_going = True
        self.on_connection_status = on_connection_status

    def stop(self):
        self._keep_going = False
        self.requests.put_nowait(None)   # sentinel to break .get()

    @property
    def connected(self):
        return self.client is not None and self.client.connected

    async def _open_connection(self):
        """Run the connection attempt in a separate thread."""
        retval = False

        if self.connected:
            await self.client.close()

        if config.is_usable:
            try:
                self.client = AsyncModbusSerialClient(
                    port=config['com_port'],
                    baudrate=config['baud'],
                    stopbits=config['stop'],
                    parity=config['parity'],
                    timeout=0.1,
                    framer=FramerType.RTU
                )

                retval = await self.client.connect()
                logger.info("Modbus client connected")
            except (ModbusException, ValueError) as e:
                logger.error(f"Error connecting to Modbus client: {e}")

        return retval

    async def run_async(self):
        """
        Main loop of the agent.
        The purpose of the agent is to handle 1 request at a time.
        """
        try:
            while self._keep_going:
                if not self.connected:
                    connection = await self._open_connection()
                    self.on_connection_status(connection)

                request: Request = await self.requests.get()

                try:
                    await request.execute(self.client)
                except Exception as ex:  # noqa: BLE001
                    logger.error(f"Request error: {ex}")

        except asyncio.CancelledError:
            logger.info("Agent cancelled - exiting")
        except Exception as e:
            logger.error(f"ModbusAgent encountered an error: {e}")

    def request(self, request: Request):
        self.requests.put_nowait(request)
