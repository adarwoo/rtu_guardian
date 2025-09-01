from enum import Enum, auto

class RequestKind(Enum):
    READ_COILS = auto()
    WRITE_COILS = auto()
    WRITE_COIL = auto()
    WRITE_HOLDING_REGISTERS = auto()
    READ_HOLDING = auto()
    READ_INPUT_REGISTERS = auto()
    OPEN = auto()


class Request:
    """Represents a request to the Modbus task."""
    def __init__(self, kind: RequestKind, address: int=0, count: int = 0, value=None):
        self.kind = kind      # e.g., "read" or "write"
        self.address = address
        self.count = count
        self.value = value