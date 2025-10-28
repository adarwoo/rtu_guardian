from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Vertical
from textual.reactive import reactive

class StaticStatusList(Widget):
    """A non-interactive vertical list of items, each can go red based on bin_status bits."""

    DEFAULT_CSS = """
        StaticStatusList {
            background: $surface;
            color: $foreground;
            padding: 1 1;
            border: round $primary;
            width: 100%;
            height: auto;
            scrollbar-size-horizontal: 0;

            Static {
                padding: 0 1;
                width: 100%;
                height: 1;
                color: $secondary-muted;

                &.error {
                    color: black;
                    background: red;
                }
            }
        }

    """

    bin_status = reactive(0)

    def __init__(self, items: list[str], *, id: str = None, classes: str = None):
        super().__init__(id=id, classes=classes)
        self.items = items
        self._statics = []
        self.map_pos = {}

    def compose(self):
        with Vertical():
            self._statics = []
            for i, label in enumerate(self.items):
                if label is None:
                    continue
                static = Static(label, classes="status-list-item-idle")
                self._statics.append(static)
                self.map_pos[i] = static
                yield static

    def watch_bin_status(self, value: int):
        # Update the style of each item based on the corresponding bit in bin_status
        for i, static in self.map_pos.items():
            if (value >> i) & 1:
                static.add_class("error")
            else:
                static.remove_class("error")
            static.refresh()