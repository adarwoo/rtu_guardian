import os
from textual.features import parse_features

from .ui.app import RTUGuardian
from .config import config
from .optargs import options


if options.debug:
    os.environ["DEBUG"] = "1"

if options.comport:
    # Override the config one
    config["com_port"] = options.comport

def main():
    RTUGuardian().run()

if __name__ == '__main__':
    if os.environ.get("DEBUG", 0):
        features = set(parse_features(os.environ.get("TEXTUAL", "")))
        features.add("debug")
        features.add("devtools")

        os.environ["TEXTUAL"] = ",".join(sorted(features))

    main()
