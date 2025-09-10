import optparse

from .config import VALID_BAUD_RATES


# Parse command line options
parser = optparse.OptionParser()

parser.set_usage("usage: %prog [options] device_id [device_id ...]")

parser.add_option("-d", "--debug", action="store_true", dest="debug", default=False,
    help="Enable debug mode")

parser.add_option("-c", "--comport", dest="comport", default=None,
    help="Specify the comport to use")

def validate_baudrate(option, opt_str, value, parser):
    try:
        baud = int(value)
        if baud not in VALID_BAUD_RATES:
            raise ValueError
        setattr(parser.values, option.dest, baud)
    except Exception:
        parser.error(f"Invalid baudrate: {value}. Valid values are: {', '.join(map(str, VALID_BAUD_RATES))}.")

parser.add_option("-b", "--baudrate", dest="baudrate", default=None, type="string",
    action="callback", callback=validate_baudrate,
    help="Specify the baudrate (e.g., 9600, 19200, 115200)")

parser.add_option("-s", "--serial", dest="serial", default=None,
    help="Specify the serial configuration. Valid values are: 8N1, 8O1, 8E1, 8N2, 8O2, 8E2."
)

parser.add_option("-z", "--zero", dest="zero", default=False, action="store_true",
    help="Start with no devices, ignoring devices from the previous session.")

(options, args) = parser.parse_args()

# Validate device IDs from command line arguments
device_ids = []

for arg in args:
    try:
        device_id = int(arg)
        
        if 1 <= device_id <= 246:
            device_ids.append(device_id)
        else:
            parser.error(f"Invalid device ID: {arg}. Valid values are 1 to 246.")
    except ValueError:
        parser.error(f"Invalid device ID: {arg}. Must be an integer between 1 and 246.")
