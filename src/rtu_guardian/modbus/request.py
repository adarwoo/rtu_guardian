from abc import ABC, abstractmethod
from typing import Any, Callable, Awaitable, Optional

from pymodbus.client import AsyncModbusSerialClient
from pymodbus.exceptions import ModbusException, ModbusIOException
import inspect

CallbackType = Callable[[Any], Any]

class Request(ABC):
    """Base Modbus request passed to the ModbusAgent queue.

    Each request may optionally provide a callback (invoked with the result of
    ``execute``) and an errback (invoked with the raised exception).
    Callbacks may be sync or async functions.
    """
    def __init__(
        self,
        device_id: int,
        data_handler: Callable[[Any], Awaitable[None]] = None,
        *,
        on_error: Optional[Callable[[], Awaitable[None]]] = None,
        on_no_response: Optional[Callable[[], Awaitable[None]]] = None,
        on_comm_loss: Optional[Callable[[], Awaitable[None]]] = None,
        **kwargs
    ):
        self.device_id = device_id
        self.data_handler = data_handler
        self.on_error = on_error
        self.on_no_response = on_no_response
        self.on_comm_loss = on_comm_loss

        # Add args from ADD_ARGS if found, using the default values
        add_args = getattr(self.__class__, "ADD_ARGS", {})
        for k, v in add_args.items():
            setattr(self, k, kwargs.get(k, v))

    @abstractmethod
    async def on_execute(self, client: AsyncModbusSerialClient) -> Any:  # pragma: no cover - interface
        """Execute the Modbus request and return a result."""

    async def execute(self, client: AsyncModbusSerialClient):
        """Wraps the execution by checking the Modbus client state, and handling any exceptions"""
        if client is None or client.connected is False:
            await self.on_comm_loss()
        else:
            try:
                retval = await self.on_execute(client)

                if retval.isError() and self.on_error:
                    self.on_error(retval.exception_code)
                elif self.data_handler:
                    res = self.data_handler(retval)
                    if inspect.isawaitable(res):
                        await res

            except ModbusIOException as e:
                if self.on_no_response:
                    res = self.on_no_response()
                    if inspect.isawaitable(res):
                        await res

            except ModbusException as e:
                if self.on_error:
                    res = self.on_error(str(e))
                    if inspect.isawaitable(res):
                        await res

            except Exception as e:
                assert(False)


class ReportDeviceId(Request):
    """
    Modbus Function Code 17
    Request the device ID (also acts as a ping).
    """
    async def on_execute(self, client: AsyncModbusSerialClient):
        return await client.report_device_id(device_id=self.device_id)

class ReadHoldingRegisters(Request):
    ADD_ARGS = {'address': 0, 'count': 1}

    async def on_execute(self, client: AsyncModbusSerialClient):
        return await client.read_holding_registers(
            self.address,
            device_id=self.device_id,
            count=self.count
        )

class ReadInputRegisters(Request):
    ADD_ARGS = {'address': 0, 'count': 1}

    async def on_execute(self, client: AsyncModbusSerialClient):
        return await client.read_input_registers(
            self.address,
            device_id=self.device_id,
            count=self.count
        )

class ReadCoils(Request):
    ADD_ARGS = {'address': 0, 'count': 1}

    """
    Modbus Function Code 1
    Read coils (digital outputs).
    """
    async def on_execute(self, client: AsyncModbusSerialClient):
        return await client.read_coils(
            device_id=self.device_id,
            address=self.address,
            count=self.count
        )

class ReadDeviceInformation(Request):
    """
    Modbus Function code 0x2B/0x0E
    """
    ADD_ARGS = {'read_code': 1, 'object_id': 0}

    async def on_execute(self, client):
        return await client.read_device_information(
            device_id=self.device_id,
            read_code=self.read_code,
            object_id=self.object_id
        )

class WriteHoldingRegisters(Request):
    """
    Modbus Function Code 16
    Write multiple holding registers.
    """
    ADD_ARGS = {'address': 0, 'values': []}

    async def on_execute(self, client: AsyncModbusSerialClient):
        return await client.write_registers(
            self.address,
            self.values,
            device_id=self.device_id,
        )

class WriteSingleRegister(Request):
    """
    Modbus Function Code 6
    Write a single holding register.
    """
    ADD_ARGS = {'address': 0, 'value': 0}

    async def on_execute(self, client: AsyncModbusSerialClient):
        return await client.write_register(
            self.address,
            self.value,
            device_id=self.device_id
        )

class WriteSingleCoil(Request):
    """
    Modbus Function Code 5
    Write a single coil (digital output).
    """
    ADD_ARGS = {'address': 0, 'value': False}

    async def on_execute(self, client: AsyncModbusSerialClient):
        return await client.write_coil(
            self.address,
            self.value,
            device_id=self.device_id
        )

class WriteCoils(Request):
    """
    Modbus Function Code 15
    Write multiple coils (digital outputs).
    """
    ADD_ARGS = {'address': 0, 'values': []}

    async def on_execute(self, client: AsyncModbusSerialClient):
        return await client.write_coils(
            self.address,
            self.values,
            device_id=self.device_id
        )

class WriteMultipleRegisters(Request):
    """
    Modbus Function Code 16
    Write multiple holding registers.
    """
    ADD_ARGS = {'address': 0, 'values': []}

    async def on_execute(self, client: AsyncModbusSerialClient):
        return await client.write_registers(
            self.address,
            self.values,
            device_id=self.device_id
        )

class CustomRequest(Request):
    """
    A custom Modbus request using a user-provided function.
    The function should accept the client and device_id as parameters.
    """
    ADD_ARGS = {'pdu': None}

    async def on_execute(self, client: AsyncModbusSerialClient):
        if self.pdu is None:
            raise ValueError("pdu must be provided for CustomRequest")

        # Append device_id to the pdu if necessary
        self.pdu.dev_id = self.device_id

        return await client.execute(False, self.pdu)

class ReadDiscreteInputs(Request):
    ADD_ARGS = {'address': 0, 'count': 1}

    """
    Modbus Function Code 2
    Read discrete inputs (digital inputs).
    """
    async def on_execute(self, client: AsyncModbusSerialClient):
        return await client.read_discrete_inputs(
            device_id=self.device_id,
            address=self.address,
            count=self.count
        )