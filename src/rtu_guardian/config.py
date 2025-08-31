import os

import serial.tools.list_ports
import toml
from asyncio.log import logger
from appdirs import user_config_dir

from .exceptions import TerminalError


APP_NAME = "relay_guardian"
CONFIG_FILENAME = "config.toml"

# Config schema with defaults
CONFIG_SCHEMA = {
    "com_port": "", # Empty string means ask on startup
    "baud": 9600,
    "stop": 1,
    "parity": "N",
    "last_device_id": 0,
    "last_com_port": "" # Last used port, will be offered as default - if still avail - next time
}

VALID_BAUD_RATES = [300, 600, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]


class Config(dict):
    """Global configuration manager for Relay Guardian, behaves like a dict."""

    def __init__(self):
        super().__init__(CONFIG_SCHEMA.copy())
        self._is_changed = False
        self._is_default = True
        self._load()

    @property
    def is_default(self):
        return self._is_default

    @property
    def is_changed(self):
        return self._is_changed

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
        try:
            with open(self._get_config_path(), "w") as f:
                toml.dump(dict(self), f)
                logger.info("Configuration saved successfully.")
                self._is_changed = False
                self._is_default = False
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")

    def _load(self):
        """Load config from disk, validate, and update the dict."""
        config_path = self._get_config_path()
        merged = CONFIG_SCHEMA.copy()

        # List available COM ports
        ports = Config.list_comports()

        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    loaded = toml.load(f)
                    merged.update(loaded)
            except toml.TomlDecodeError as e:
                logger.error(f"Error loading configuration: {e}")
            except Exception as e:
                logger.error(f"Unexpected error loading configuration: {e}")
            else:
                try:
                    self._validate_config(merged)
                    self._is_default = False
                except ValueError as e:
                    logger.error(f"Configuration error: {e}")
                    # Revert to default
                    merged = CONFIG_SCHEMA.copy()

            # Does the com port exists?
            if merged["com_port"] not in ports:
                merged["com_port"] = "" # Let the user choose
                self._is_changed = True
            else:
                # Copy to the last
                merged["last_com_port"] = merged["com_port"]

        # Set the last_comport
        if merged["last_com_port"] not in ports:
            merged["last_com_port"] = ports[0] if ports else ""

        self.clear()
        self.update(merged)

    def update(self, *args, **kwargs):
        # Make a copy to compare with later
        old = self.copy()

        super().update(*args, **kwargs)

        # Copy the last_com_port since it is not to be compared
        old["last_com_port"] = self["last_com_port"]

        self._is_changed = (old != self)


# Global config dictionary, always valid and up-to-date
config = Config()
