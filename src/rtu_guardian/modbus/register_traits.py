from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence
from enum import Enum

from pymodbus.pdu import ModbusPDU

from rtu_guardian.modbus.request import (
    ReadInputRegisters, ReadHoldingRegisters,
    WriteSingleRegister, WriteMultipleRegisters
)


# ---------------------------------------------------------------------------
# Core definitions
# ---------------------------------------------------------------------------

class RegisterKind(Enum):
    INPUT = "input"
    HOLDING = "holding"


@dataclass(frozen=True)
class RegisterRef:
    group: str
    name: str
    address: int
    size: int = 1
    kind: RegisterKind = RegisterKind.HOLDING

    def __repr__(self) -> str:
        return f"<{self.group}.{self.name}@0x{self.address:04X}>"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_registers(
    cls,
    kind: RegisterKind,
) -> dict[str, RegisterRef]:
    """Collect UPPER_CASE class attributes into sorted RegisterRefs."""
    registry: dict[str, RegisterRef] = {}

    for k, v in cls.__dict__.items():
        if k.isupper() and isinstance(v, int):
            ref = RegisterRef(group=cls.__name__, name=k, address=v, kind=kind)
            registry[k] = ref
        elif k.isupper() and isinstance(v, (list, tuple)):
            addr_list = list(v)
            if not all(isinstance(a, int) for a in addr_list):
                raise TypeError(f"All items in {cls.__name__}.{k} must be integers")
            if len(addr_list) < 1:
                raise ValueError(f"{cls.__name__}.{k} must have at least one address")

            start_addr = addr_list[0]
            size = len(addr_list)
            ref = RegisterRef(group=cls.__name__, name=k, address=start_addr, size=size, kind=kind)
            registry[k] = ref

    return dict(sorted(registry.items(), key=lambda item: item[1].address))


def _attach_registry_api(cls, registry: dict[str, RegisterRef]):
    """Attach helper APIs to the class."""
    cls._registry = registry

    @classmethod
    def all(cls) -> Sequence[RegisterRef]:
        return list(cls._registry.values())

    @classmethod
    def by_name(cls, name: str) -> RegisterRef:
        return cls._registry[name.upper()]

    @classmethod
    def by_address(cls, address: int) -> RegisterRef:
        for ref in cls._registry.values():
            if ref.address == address:
                return ref
        raise KeyError(address)

    cls.all = all
    cls.by_name = by_name
    cls.by_address = by_address
    return cls


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def modbus_input_registers(readable: bool = True):
    """Decorator for input register groups (read-only)."""
    def wrapper(cls):
        registry = _collect_registers(cls, RegisterKind.INPUT)
        _attach_registry_api(cls, registry)
        cls._KIND = RegisterKind.INPUT
        cls._WRITABLE = False

        if readable:
            @classmethod
            def read(cls, device_id: int, data_handler: Callable[[dict[str, int]], None], *names_or_ids, **kwargs):
                return _read_collector(cls, device_id, data_handler, ReadInputRegisters, *names_or_ids, **kwargs)
            cls.read = read

        return cls
    return wrapper


def modbus_holding_registers(
    readable: bool = True,
    single_writable: bool = False,
    group_writable: bool = False
):
    """Decorator for holding register groups (read/write)."""
    def wrapper(cls):
        writable = single_writable or group_writable
        registry = _collect_registers(cls, RegisterKind.HOLDING)
        _attach_registry_api(cls, registry)
        cls._KIND = RegisterKind.HOLDING
        cls._WRITABLE = writable

        if readable:
            @classmethod
            def read(cls, device_id: int, data_handler: Callable[[dict[str, int]], None], *names_or_ids, **kwargs):
                # If no names_or_ids provided, read all registers in the group
                if not names_or_ids:
                    names_or_ids = [ref.name for ref in cls.all()]
                return _read_collector(cls, device_id, data_handler, ReadHoldingRegisters, *names_or_ids, **kwargs)
            cls.read = read

        if single_writable:
            @classmethod
            def write_single(cls, device_id: int, register_address: int, value: int, **kwargs):
                if not (0 <= value <= 0xFFFF):
                    raise ValueError("Value must be between 0 and 65535 (0xFFFF)")
                ref = cls.by_address(register_address)
                kwargs["address"] = ref.address
                kwargs["value"] = value
                return WriteSingleRegister(device_id, **kwargs)
            cls.write_single = write_single

        if group_writable:
            @classmethod
            def write_group(cls, device_id: int, *args, **kwargs) -> WriteMultipleRegisters:
                """
                Build a WriteMultipleRegisters request.

                Supports both kwargs and a single dict argument:
                    Relays.write_group(1, relay_1_config=10, RELAY_2_CONFIG=20)
                    Relays.write_group(1, {"RELAY_1_CONFIG": 10, "RELAY_2_CONFIG": 20})
                    Relays.write_group(1, {0x0020: 10, 0x0021: 20})

                Keys may be:
                    - uppercase or lowercase register names (string)
                    - integer addresses
                """
                # Collect key/value pairs
                if args and isinstance(args[0], dict):
                    items = args[0].items()
                else:
                    items = kwargs.items()

                if not items:
                    raise ValueError("At least one register/value pair required")

                resolved: list[tuple[int, int, int, RegisterRef]] = []

                for key, value in items:
                    if isinstance(key, str):
                        # normalize case
                        ref = cls.by_name(key.upper())
                    elif isinstance(key, int):
                        ref = cls.by_address(key)
                    else:
                        raise TypeError(f"Invalid register key: {key!r}")

                    if not ref.writable:
                        raise ValueError(f"Register '{ref.name}' is not writable")

                    resolved.append((ref.address, ref.size, value, ref))

                # Sort by address
                resolved.sort(key=lambda t: t[0])
                addresses = [r[0] for r in resolved]
                start = addresses[0]

                # Validate contiguity
                for i in range(len(resolved) - 1):
                    curr_addr, curr_size, _, curr_ref = resolved[i]
                    next_addr, _, _, _ = resolved[i + 1]
                    if next_addr != curr_addr + curr_size:
                        raise ValueError(
                            f"Registers must be contiguous; got 0x{curr_addr:04X} "
                            f"(size {curr_ref.size}) then 0x{next_addr:04X}"
                        )

                # Pack values
                ordered_values: list[int] = []
                for _, size, value, _ in resolved:
                    if size == 1:
                        ordered_values.append(value)
                    elif size == 2 and isinstance(value, int):
                        # Split 32-bit int into two 16-bit words
                        ordered_values.extend([(value >> 16) & 0xFFFF, value & 0xFFFF])
                    elif size > 1 and isinstance(value, (list, tuple)) and len(value) == size:
                        ordered_values.extend(value)
                    else:
                        raise ValueError(
                            f"Value for multi-word register must be int (for size==2) "
                            f"or sequence of length {size}"
                        )

                return WriteMultipleRegisters(device_id, start, ordered_values)
            def write_group(cls, device_id: int, **kwargs: int):
                if not kwargs:
                    raise ValueError("At least one register name/value pair required")

                resolved = []
                for name, value in kwargs.items():
                    ref = cls.by_name(name)
                    if not ref.writable:
                        raise ValueError(f"Register '{name}' is not writable")
                    resolved.append((ref.address, ref.size, value, ref))

                resolved.sort(key=lambda t: t[0])
                addresses = [r[0] for r in resolved]
                start = addresses[0]

                # validate contiguity
                for i in range(len(resolved) - 1):
                    curr_addr, curr_size, curr_ref = resolved[i]
                    next_addr, _, _ = resolved[i + 1]
                    if next_addr != curr_addr + curr_size:
                        raise ValueError(
                            f"Registers must be contiguous; got 0x{curr_addr:04X} "
                            f"(size {curr_ref.size}) then 0x{next_addr:04X}"
                        )

                ordered_values = []
                for _, size, value, _ in resolved:
                    if size == 1:
                        ordered_values.append(value)
                    elif size == 2 and isinstance(value, int):
                        ordered_values.extend([(value >> 16) & 0xFFFF, value & 0xFFFF])
                    elif size > 1 and isinstance(value, (list, tuple)) and len(value) == size:
                        ordered_values.extend(value)
                    else:
                        raise ValueError(
                            f"Value for multi-word register must be int (for size==2) "
                            f"or sequence of length {size}"
                        )

                return WriteMultipleRegisters(device_id, start, ordered_values)

            cls.write_group = write_group

        return cls
    return wrapper


# ---------------------------------------------------------------------------
# Read collector (shared)
# ---------------------------------------------------------------------------

def _pdu_decoder(
    data_handler: Callable[[dict[str, int]], None],
    REFS: list[RegisterRef],
    pdu: ModbusPDU) -> None:

    result: dict[str, int] = {}
    if not REFS:
        if data_handler:
            data_handler(result)
        return

    addresses = [ref.address for ref in REFS]
    start_addr = min(addresses)

    for ref in REFS:
        offset = ref.address - start_addr
        if ref.size == 1:
            value = pdu.registers[offset]
        elif ref.size == 2:
            high = pdu.registers[offset]
            low = pdu.registers[offset + 1]
            value = (high << 16) | low
        else:
            value = 0
            for i in range(ref.size):
                value = (value << 16) | pdu.registers[offset + i]
        result[ref.name.lower()] = value

    data_handler(result)


def _read_collector(
    cls,
    device_id: int,
    data_handler: Callable[[dict[str, int]], None],
    request_type: type[ReadInputRegisters | ReadHoldingRegisters],
    *names_or_ids: (str | int),
    **kwargs
):
    if len(names_or_ids) == 0:
        refs = cls.all()
    else:
        refs = []
        for name_or_id in names_or_ids:
            if isinstance(name_or_id, str):
                ref = cls.by_name(name_or_id.upper())
            elif isinstance(name_or_id, (list, tuple)):
                ref = cls.by_address(name_or_id[0])
            else:
                ref = cls.by_address(name_or_id)
            refs.append(ref)

    if not refs:
        raise ValueError("No registers to read")

    refs.sort(key=lambda r: r.address)
    start_addr = refs[0].address
    count = refs[-1].address - start_addr + refs[-1].size

    decode_pdu = lambda pdu: _pdu_decoder(data_handler, refs, pdu)

    return request_type(device_id, decode_pdu, address=start_addr, count=count, **kwargs)
