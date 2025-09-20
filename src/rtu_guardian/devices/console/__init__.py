"""Console
"""
from .console_device import ConsoleDevice

WIDGET = ConsoleDevice


def match(*, name: str="", id: int=0) -> bool:
    import re

    return all([
        id == 37,
        re.match(r"^console", name, re.IGNORECASE)
    ])
