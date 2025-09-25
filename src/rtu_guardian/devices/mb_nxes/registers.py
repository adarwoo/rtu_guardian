"""
Modbus device registers abstraction

Provides small dynamic helper classes so UI / logic can read and write
registers without hard-coding request logic everywhere.
Maintains a single source of truth for register addresses and types.
"""
from __future__ import annotations
from enum import Enum

from rtu_guardian.modbus.register_traits import (
    modbus_input_registers,
    modbus_holding_registers,
)

# -----------------------------------------------------------------------------
# Constants mapping
# -----------------------------------------------------------------------------
class InfeedType(Enum):
    BELOW_THRESHOLD = 0
    DC = 1
    AC = 2

class ParityType(Enum):
    NONE = 0
    EVEN = 1
    ODD = 2

class StopBitsType(Enum):
    ONE = 0
    TWO = 1

class BaudRateType(Enum):
    BAUD_9600 = 0
    BAUD_19200 = 1
    BAUD_38400 = 2
    BAUD_57600 = 3
    BAUD_115200 = 4

class EStopControlMode(Enum):
    PULSED = 0
    RESETTABLE = 1
    TERMINAL = 2

class RelayDiagnosticValues(Enum):
    OK = 0
    FAULTY = 1
    DISABLED = 2

class DeviceStatus(Enum):
    OPERATIONAL = 0
    ESTOP = 1
    TERMINAL = 2

# -----------------------------------------------------------------------------
# Modbus Register mappings (decorator-based)
# -----------------------------------------------------------------------------
@modbus_input_registers()
class StatusAndMonitoring:
    STATUS           = 0x0008
    RUNNING_MINUTES  = [0x0009, 0x000A]
    INFEED_TYPE      = 0x000B
    INFEED_VOLTAGE   = 0x000C
    INFEED_LOWEST    = 0x000D
    DEVICE_HEALTH    = 0x000F
    INFEED_HIGHEST   = 0x000E
    DEVICE_HEALTH    = 0x000F
    ESTOP_CAUSE      = 0x0010
    DIAGNOSTIC_CODE  = 0x0011

@modbus_input_registers()
class RelayDiagnostics:
    RELAY_1_CYCLES  = [0x0019, 0x001A]
    RELAY_1_DIAG    = 0x0018
    RELAY_2_CYCLES  = [0x001C, 0x001D]
    RELAY_2_DIAG    = 0x001B
    RELAY_3_CYCLES  = [0x001F, 0x0020]
    RELAY_3_DIAG    = 0x001E


@modbus_holding_registers(readable=True, group_writable=True)
class CommunicationSettings:
    BAUD_RATE       = 0x0001
    DEVICE_ADDRESS  = 0x0000
    PARITY          = 0x0002
    STOP_BITS       = 0x0003


@modbus_holding_registers(readable=True, group_writable=True)
class PowerInfeed:
    HIGH_THRESHOLD  = 0x000A
    LOW_THRESHOLD   = 0x0009
    TYPE            = 0x0008


@modbus_holding_registers(readable=True, single_writable=True)
class SafetyLogic:
    ESTOP_ON_UNDER_VOLTAGE = 0x0010
    ESTOP_ON_OVER_VOLTAGE = 0x0011
    ESTOP_ON_INCORRECT_VOLTAGE_TYPE = 0x0012
    ESTOP_ON_COMM_LOST = 0x0013
    INFEED_FAULT_RELAY_MASK = 0x0014
    COMM_LOST_RELAY_MASK = 0x0015


@modbus_holding_registers(readable=True, single_writable=True)
class Relays:
    RELAY_1_CONFIG = 0x0018
    RELAY_2_CONFIG = 0x0019
    RELAY_3_CONFIG = 0x001A


@modbus_holding_registers(single_writable=True)
class DeviceControl:
    SET_RESET_ESTOP              = 0x0064
    ZERO_MEASUREMENTS            = 0x0065
    LOCATE                       = 0x0066
    RESET_TO_FACTORY_DEFAULTS    = 0x0067
    EXIT_RECOVERY_MODE           = 0x0068
    DEVICE_RESET                 = 0x0069

DEVICE_CONTROL_UNLOCK = 0x0AA55
DEVICE_CONTROL_RESET = 0x0000
DEVICE_CONTROL_PULSE = 0x1100
DEVICE_CONTROL_ESTOP = 0x2200
DEVICE_CONTROL_TERMINAL = 0xFF00
DEVICE_CONTROL_RESET_CONFIG = 0x178C