from textual.widgets import Header as Hdr, Label
from textual.reactive import reactive

from ..config import config

class Header(Hdr):
    def compose(self):
        yield from super().compose()

        com_str = (
            f"COM{config['last_com_port']}:{config['baud']}@8{config['parity']}{config['stop']}"
        )

        yield Label(com_str, id="comm")
