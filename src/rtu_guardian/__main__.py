import asyncio
import faulthandler
import logging
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

    faulthandler.enable()
    os.environ["PYTHONASYNCIODEBUG"] = "1"
    asyncio.get_event_loop().set_debug(True)

    import sys, logging
    def hook(exc_type, exc, tb):
        logging.error("Uncaught top-level", exc_info=(exc_type, exc, tb))
    sys.excepthook = hook

async def main():
    await RTUGuardian().run_async()


if __name__ == '__main__':
    setup_debug()
    asyncio.run(main())
