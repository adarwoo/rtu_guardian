import types
import pytest

from rtu_guardian.modbus.register_traits import (
    RegisterKind,
    InputReadable,
    HoldingReadable,
    HoldingSingleWritable,
    HoldingGroupWritable,
    RegisterRef,
    _pdu_decoder,
)
from rtu_guardian.modbus.request import (
    ReadInputRegisters,
    ReadHoldingRegisters,
    WriteSingleRegister,
    WriteMultipleRegisters,
)


class ExampleInputs(InputReadable):
    TEMP = 0x0001
    HUM = 0x0002
    FLOW = 0x0003


class ExampleHolding(HoldingSingleWritable):
    A = 0x0010
    B = 0x0011
    C = 0x0012


class ExampleHoldingGroup(HoldingGroupWritable):
    X = 0x0020
    Y = 0x0021
    Z = 0x0022


def test_meta_collects_registers_sorted():
    refs = ExampleInputs.all()
    assert [r.name for r in refs] == ["TEMP", "HUM", "FLOW"]
    assert all(isinstance(r, RegisterRef) for r in refs)


def test_build_read_inputs_spans_range():
    req = ExampleInputs.build_read(5, "TEMP", "FLOW")
    assert isinstance(req, ReadInputRegisters)
    # Should start at lowest (0x0001) and count cover TEMP..FLOW (3 regs)
    assert req.address == 0x0001
    assert req.count == 3


def test_decoder_maps_all_values():
    refs = list(ExampleInputs.all())
    # Fake PDU object with .registers attribute
    pdu = types.SimpleNamespace(registers=[11, 22, 33])
    captured = {}
    _pdu_decoder(refs, pdu, lambda m: captured.update(m))
    assert captured == {"temp": 11, "hum": 22, "flow": 33}


def test_single_write_request():
    req = ExampleHolding.build_write(7, "B", 123)
    assert isinstance(req, WriteSingleRegister)
    assert req.address == 0x0011
    assert req.value == 123


def test_group_multi_write_success():
    req = ExampleHoldingGroup.build_write_multiple(9, X=1, Y=2, Z=3)
    assert isinstance(req, WriteMultipleRegisters)
    assert req.address == 0x0020
    assert req.values == [1, 2, 3]


def test_group_multi_write_non_contiguous_raises():
    class GapGroup(HoldingGroupWritable):
        A = 0x0100
        B = 0x0102  # gap (0x0101 missing)

    with pytest.raises(ValueError):
        GapGroup.build_write_multiple(1, A=10, B=20)


def test_build_write_mapping_equivalent():
    req1 = ExampleHoldingGroup.build_write_multiple(2, X=5, Y=6)
    req2 = ExampleHoldingGroup.build_write_mapping(2, {"Y": 6, "X": 5})
    # Order should normalize and produce same starting addr / values sorted by address
    assert req1.address == req2.address == 0x0020
    assert req1.values == [5, 6]
    assert req2.values == [5, 6]
