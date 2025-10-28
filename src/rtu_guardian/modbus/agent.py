import asyncio
from asyncio.log import logger

from pymodbus import FramerType, ModbusException
from pymodbus.client import AsyncModbusSerialClient

from rtu_guardian.config import config
from rtu_guardian.modbus.request import Request
from rtu_guardian.constants import MODBUS_TIMEOUT


class ModbusAgent:
    def __init__(
        self,
        requests: asyncio.Queue[Request],
        on_connection_status: callable,
        recovery_mode: bool=False
    ):
        self.requests = requests
        self.client: AsyncModbusSerialClient | None = None
        self._app = None
        self.on_connection_status = on_connection_status
        self._recovery_mode = recovery_mode

    @property
    def connected(self):
        return self.client is not None and self.client.connected

    async def _open_connection(self):
        """Run the connection attempt in a separate thread."""
        retval = False

        if self.connected:
            await self.client.close()

        try:
            if self._recovery_mode is True:
                logger.info("Starting ModbusAgent in recovery mode")

                self.client = AsyncModbusSerialClient(
                    port=config['com_port'],
                    baudrate=9600,
                    stopbits=1,
                    parity='N',
                    timeout=MODBUS_TIMEOUT,
                    retries=1,
                    framer=FramerType.RTU
                )
            elif config.is_usable:
                self.client = AsyncModbusSerialClient(
                    port=config['com_port'],
                    baudrate=config['baud'],
                    stopbits=config['stop'],
                    parity=config['parity'],
                    timeout=MODBUS_TIMEOUT,
                    retries=1,
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
            while True:
                if not self.connected:
                    connection = await self._open_connection()
                    self.on_connection_status(connection)

                if not self.connected:
                    await asyncio.sleep(1)
                    continue

                request: Request = await self.requests.get()

                if request is None:  # Sentinel to stop
                    break

                try:
                    await request.execute(self.client)
                except Exception as ex:  # noqa: BLE001
                    logger.error(f"Request error: {ex}")

        except asyncio.CancelledError:
            logger.info("Agent cancelled - exiting")

            # Close the client connection gracefully
            if self.client is not None and self.client.connected:
                self.client.close()
        except Exception as e:
            logger.error(f"ModbusAgent encountered an error: {e}")

    def request(self, request: Request):
        if self.client.connected:
            self.requests.put_nowait(request)
