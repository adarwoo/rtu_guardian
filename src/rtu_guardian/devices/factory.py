from __future__ import annotations

import importlib
import logging
import pkgutil
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable, Type

import rtu_guardian.devices as devices_pkg
from rtu_guardian.devices.console import match

log = logging.getLogger(__name__)


@dataclass
class DiscoveredDevice:
    """Metadata describing a device package discovered by the factory."""
    type: str
    module: ModuleType
    widget: Type[Any]
    match: Callable[[Any], bool|None]


class DeviceFactory:
    """Factory that discovers device packages and instantiates their widgets.

    Contract for each device package (e.g., rtu_guardian.devices.relay_es):
    - Must be a Python package (contains __init__.py)
    - Expose an `identify(scanner) -> bool` function used by the scanner
    - Expose a `WIDGET` attribute referencing the widget/container class to instantiate
    """

    def __init__(self) -> None:
        self._devices: list[DiscoveredDevice] = []
        self._discover_devices()

    @property
    def devices(self) -> tuple[DiscoveredDevice, ...]:
        return tuple(self._devices)

    def _discover_devices(self) -> None:
        self._devices.clear()

        # Iterate first-level subpackages under rtu_guardian.devices
        for _, name, ispkg in pkgutil.iter_modules(devices_pkg.__path__):
            if not ispkg:
                continue

            fqmn = f"{devices_pkg.__name__}.{name}"

            try:
                module = importlib.import_module(fqmn)
            except Exception as exc:
                log.exception("Failed to import device package %s", fqmn, exc_info=exc)
                continue

            match_fn = getattr(module, "match", None)
            widget_cls = getattr(module, "WIDGET", None)

            if not callable(match_fn) or widget_cls is None:
                log.error("Skipping %s (missing match() or WIDGET)", fqmn)
                continue

            self._devices.append(
                DiscoveredDevice(type=name, module=module, widget=widget_cls, match=match_fn)  # type: ignore[arg-type]
            )

        # Stable order: sort by type for deterministic behavior
        self._devices.sort(key=lambda d: d.type)

    def match(self, candidates: list[DiscoveredDevice], type: str, **kwargs) -> list[DiscoveredDevice]:
        """
        Return a list of remaining possible candidates.
        If the list has only one element, it is a match.
        Pass the list again with the reduced list until one or none remain.
        """
        remaining_candidates = candidates.copy() if candidates else self._devices.copy()
        retval = []

        for dev in remaining_candidates:
            match = False

            try:
                match = dev.match(**kwargs)
            except Exception as exc:
                log.exception("identify() raised for %s", dev.name, exc_info=exc)

            if match == False:
                continue

            retval.append(dev)

        return retval

    def create_widget(self, device: DiscoveredDevice, *args: Any, **kwargs: Any) -> Any:
        """Instantiate the device's widget class with provided args/kwargs."""
        return device.widget(*args, **kwargs)


# Singleton instance for convenience
factory = DeviceFactory()
