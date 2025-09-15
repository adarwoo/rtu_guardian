import asyncio
import inspect
import logging

from functools import wraps

def modbus_poller(interval=0.5):
    def decorator(cls):
        orig_init = cls.__init__
        orig_on_show = getattr(cls, "on_show", None)
        orig_on_hide = getattr(cls, "on_hide", None)

        @wraps(orig_init)
        def __init__(self, *args, **kwargs):
            orig_init(self, *args, **kwargs)
            self._refresh_interval = interval
            self._update_task = None
            self._active = False

        async def _refresh_loop(self):
            try:
                while self._active:
                    self.on_poll()
                    await asyncio.sleep(self._refresh_interval)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logging.getLogger("textual").error(f"Error during refresh: {e}")

        async def on_show(self):
            self._active = True
            self._update_task = asyncio.create_task(self._refresh_loop())

            if orig_on_show:
                if inspect.iscoroutinefunction(orig_on_show):
                    await orig_on_show(self)
                else:
                    orig_on_show(self)

        async def on_hide(self):
            self._active = False

            if self._update_task and not self._update_task.done():
                self._update_task.cancel()

                try:
                    await self._update_task
                except asyncio.CancelledError:
                    pass
                self._update_task = None

            if orig_on_hide:
                if inspect.iscoroutinefunction(orig_on_hide):
                    await orig_on_hide(self)
                else:
                    orig_on_hide(self)

        cls.__init__ = __init__
        cls._refresh_loop = _refresh_loop
        cls.on_show = on_show
        cls.on_hide = on_hide
        return cls

    return decorator
