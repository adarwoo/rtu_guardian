"""Relay ES device package entry-point for device factory discovery.

Exposes:
- WIDGET: the widget/container class to instantiate for this device
- match: function used by the factory/scanner to identify supported devices
"""
from .pneumatic_device import PneumaticDevice

WIDGET = PneumaticDevice


def match(*, id = 0, name = "") -> bool|None:
    """Called to identify if this device matches.
    The probing sequence is:
        1. Read device_id (code 17) - get id and name
        2. If needed, read MEI (code 43) at level 3

    The factory calls this function with either type="id" or type="mei".
    The kwargs will accumulate all known information, so for MEI probing
    the kwargs will include the device_id information.

    If the function returns True, the device is definitly a match.
    If the function returns False, the device is definitly not a match.
    If the function returns None, the device is not sure and further probing
    is needed.

    For the device_id, the kwargs are:
        id (int): The device ID code, if any
        name (str): The device name string, if any

    For MEI, the kwargs are:
        mei_name (str): The device name string, if any
        mei_id (int): The device ID code, if any
        vendor_id (int): The vendor ID, if any
        product_code (int): The product code, if any
        revision (tuple[int, int]): The major/minor revision, if any
        device_id (int): The device ID code from the device_id read, if any
        extended (dict[int:int]): Any extended information from the device_id read, if any

    Args:
        type (str): device_id (code 17) or mei (code 43)

    Returns:
        bool: True if this device definitly matches
              False if this device definitely does not match
              None if unsure and further probing is needed
    """
    import re

    return all([
        id == 49,
        re.match(r"^pneumatic", name, re.IGNORECASE)
    ])
