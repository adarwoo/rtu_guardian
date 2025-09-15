import asyncio
import logging

from abc import ABC, abstractmethod

from rtu_guardian.modbus.agent import ModbusAgent

logger = logging.getLogger("textual")

class RefreshableWidget(ABC):
    def __init__(self, agent: ModbusAgent, device_address: int, refresh_interval: float = 1.0):
        super().__init__()
        self.agent = agent
        self.device_address = device_address
        self._update_task: asyncio.Task | None = None
        self._active = False
        self._refresh_interval = refresh_interval

    def on_show(self):
        self._active = True
        if self._update_task is None or self._update_task.done():
            self._update_task = asyncio.create_task(self._refresh_loop())

    def on_hide(self):
        self._active = False
        if self._update_task and not self._update_task.done():
            self._update_task.cancel()
            self._update_task = None

    async def _refresh_loop(self):
        """Override this in subclasses to implement refresh logic."""
        while self._active:
            try:
                self.on_request_data()
                await asyncio.sleep(self._refresh_interval)
            except Exception as e:
                logger.error(f"Error during refresh: {e}")

    @abstractmethod
    def on_request_data(self) -> None:
        """Override this in subclasses to implement data request logic."""
