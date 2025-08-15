import optparse
import os

from textual.features import parse_features

from .fe import RelayGuardian
from .config import config

# Parse command line options
parser = optparse.OptionParser()
parser.add_option("-d", "--debug", action="store_true", dest="debug", default=False, help="Enable debug mode")
parser.add_option("-c", "--comport", dest="comport", default=None, help="Specify the comport")

(options, args) = parser.parse_args()

if options.debug:
    os.environ["DEBUG"] = "1"

if options.comport:
    # Override the config one
    config["com_port"] = options.comport

def main():
    RelayGuardian().run()

if __name__ == '__main__':
    if os.environ.get("DEBUG", 0):
        features = set(parse_features(os.environ.get("TEXTUAL", "")))
        features.add("debug")
        features.add("devtools")

        os.environ["TEXTUAL"] = ",".join(sorted(features))

    main()
