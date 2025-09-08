import asyncio
import os

from textual.features import parse_features

from rtu_guardian.ui.app import RTUGuardian
from rtu_guardian.config import config

def setup_debug():
    from rtu_guardian.optargs import options

    if options.debug:
        os.environ["DEBUG"] = "1"

    if options.comport:
        # Override the config one
        config["com_port"] = options.comport

    if os.environ.get("DEBUG", 0):
        features = set(parse_features(os.environ.get("TEXTUAL", "")))
        features.add("debug")
        features.add("devtools")

        os.environ["TEXTUAL"] = ",".join(sorted(features))

async def main():
    setup_debug()

    app = RTUGuardian()

    # Run the Textual TUI
    await app.run_async()


if __name__ == '__main__':
    asyncio.run(main())
