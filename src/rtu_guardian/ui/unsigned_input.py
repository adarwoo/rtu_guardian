from textual.widgets import Input
from textual.events import Key


class UnsignedIntegerInput(Input):
    """An Input that only accepts non-negative integers."""

    def __init__(self, **kwargs):
        super().__init__(type="integer", **kwargs)

    async def _on_key(self, event: Key) -> None:
        # Ignore minus or plus keys
        if not event.key in ("-", "+"):
            await super()._on_key(event)

