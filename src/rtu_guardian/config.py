import os
import toml
import serial.tools.list_ports

from asyncio.log import logger
from appdirs import user_config_dir

from rtu_guardian.optargs import options, device_ids


APP_NAME = "rtu_guardian"
CONFIG_FILENAME = "config.toml"

# Config schema with defaults
CONFIG_SCHEMA = {
    "com_port": "", # Empty string means ask on startup
    "baud": 9600,
    "stop": 1,
    "parity": "N",
    "device_ids": [],
    "check_comm": True
}

# Valid baud values
VALID_BAUD_RATES = [300, 600, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]


class Config(dict):
    """Global configuration manager for Relay Guardian, behaves like a dict."""

    def __init__(self):
        super().__init__(CONFIG_SCHEMA.copy())
        self._has_unsaved_changes = False
        self._is_usable = False
        self._load()
        self.apply_command_line_overrides()

    @property
    def is_usable(self):
        return self._is_usable

    @property
    def has_unsaved_changes(self):
        return self._has_unsaved_changes

    def _validate_config(self, config=None):
        """Validate config values and raise ValueError if invalid."""
        cfg = config if config is not None else self

        if cfg["baud"] not in VALID_BAUD_RATES:
            raise ValueError(f"Invalid baud rate: {cfg['baud']}")

        if cfg["stop"] not in [1, 2]:
            raise ValueError(f"Invalid stop bits: {cfg['stop']}")

        if cfg["parity"] not in ["N", "E", "O"]:
            raise ValueError(f"Invalid parity: {cfg['parity']}")

    @staticmethod
    def _get_config_path():
        config_dir = user_config_dir(APP_NAME)
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, CONFIG_FILENAME)

    @staticmethod
    def list_comports():
        """List all sorted COM ports."""
        return sorted([p.device for p in serial.tools.list_ports.comports()],
                      key=lambda x: int(''.join(filter(str.isdigit, x)) or 0))

    def save(self):
        """Save the config dictionary to disk."""
        assert(self._is_usable)

        try:
            with open(self._get_config_path(), "w") as f:
                toml.dump(dict(self), f)
                logger.info("Configuration saved successfully.")
                self._has_unsaved_changes = False
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")

    def _load(self):
        """Load config from disk, validate, and update the dict."""
        config_path = self._get_config_path()
        config_in_the_works = CONFIG_SCHEMA.copy()

        # List available COM ports
        ports = Config.list_comports()

        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    loaded = toml.load(f)

                    # Complete any missing values
                    config_in_the_works.update(loaded)
            except toml.TomlDecodeError as e:
                logger.error(f"Error loading configuration: {e}")
            except Exception as e:
                logger.error(f"Unexpected error loading configuration: {e}")
            else:
                try:
                    self._validate_config(config_in_the_works)
                except ValueError as e:
                    logger.error(f"Configuration error: {e}")
                    # Revert to default
                    config_in_the_works = CONFIG_SCHEMA.copy()

            # Does the configuration being generated include a com port?
            if config_in_the_works["com_port"] not in ports:
                logger.warning("COM port not found, using default.")
                config_in_the_works["com_port"] = ports[-1] if ports else ""
                self._has_unsaved_changes = True
                self._is_usable = False
            else:
                self._is_usable = True

        # Apply the configuration the this object
        self.clear()
        self.update(config_in_the_works)

    def update(self, *args, **kwargs):
        # Make a copy to compare with later
        old = self.copy()

        super().update(*args, **kwargs)

        self._has_unsaved_changes = (old != self)

        # Check if the comm port is valid
        self._is_usable = self['com_port'] in Config.list_comports()

    def apply_command_line_overrides(self):
        """Apply any command line overrides to the config."""
        changed = False

        if options.comport:
            self['com_port'] = options.comport
            changed = True

        if options.baudrate:
            self['baud'] = options.baudrate
            changed = True

        if options.serial:
            serial_opt = options.serial.upper()
            if len(serial_opt) == 3 and serial_opt[0] == '8':
                self['stop'] = int(serial_opt[2])
                self['parity'] = serial_opt[1]
                changed = True

        if options.zero:
            self['device_ids'] = []
            changed = True
        elif device_ids:
            self['device_ids'] = options.device_ids
            changed = True

        if changed:
            try:
                self._validate_config()
            except ValueError as e:
                logger.error(f"Command line override error: {e}")
            else:
                self._has_unsaved_changes = True
                self._is_usable = self['com_port'] in Config.list_comports()


# Global config dictionary, always valid and up-to-date
config = Config()
