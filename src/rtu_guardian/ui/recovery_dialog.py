import asyncio
import re
import time
from typing import Dict

from textual import on
from textual.screen import ModalScreen
from textual.widgets import Button, LoadingIndicator, Label, Switch
from textual.containers import Vertical, Horizontal
from textual.message import Message

from pymodbus.pdu.mei_message import ReadDeviceInformationResponse

from rtu_guardian.constants import RECOVERY_ID
from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.modbus.request import ReadDeviceInformation, ReadHoldingRegisters, WriteHoldingRegisters
from rtu_guardian.config import config, VALID_BAUD_RATES

from textual.widgets import Input
from textual.widgets import Button, LoadingIndicator, Label, Input, Select, Checkbox
from textual.containers import Vertical, Horizontal, VerticalScroll, Grid

from rtu_guardian.recovery_helper import CommParams, RecoveryHelper, parity_to_string



INFO = """
[b]To recover a device, follow these steps:[/b]
1. Make sure the device is powered on.
2. Make sure it is properly connected to the RS485.
   In case of doubt, run a scan of the bus and check the device Modbus Rx LED.
   It must show some regular activity. If not, try a different cable or port.
3. Press and hold the EStop button until all LEDs start flashing.
4. Wait for device identification to complete.
5. If the device supports recovery, click [i]'Recover'[/i] to start the recovery process.
"""


class Confirmed(Message):
    def __init__(self, result: dict | None) -> None:
        super().__init__()
        self.result = result

class RecoveryScanningDialog(ModalScreen):
    """Dialog to scan for a device in recovery mode and optionally start recovery."""
    CSS_PATH = "css/recovery_dialog.tcss"

    def __init__(self):
        super().__init__()

        # Create a Modbus agent in recovery mode
        self.modbus_agent = ModbusAgent(self.on_connection_status, True)

        # Start the worker to cancel on dismiss
        self._worker = None
        self._scanner_worker = None

        # Retry logic
        self.start_time = None
        self.retry_timeout = 60.0  # 1 minute timeout
        self.retry_interval = 2.0  # 2 second between retries
        self.attempt_count = 0

        # Last message log
        self.last_message = []
        self.comm_params = None

    def compose(self):
        cancel = Button("Cancel", id="cancel")
        self.recover = Button("Recover", id="recover", variant="success")
        # Start hidden; enable/show only when a recoverable device is identified
        self.recover.visible = False

        with Vertical(id="recovery-dialog"):
            yield Label(INFO, id="recovery-info")
            yield LoadingIndicator(id="loading")
            yield Horizontal(cancel, self.recover, classes="dialog-buttons")

    async def on_button_pressed(self, event):
        if event.button.id == "cancel":
            self.modbus_agent.request(None)
            await self._worker.wait()
            self.dismiss(None)
        elif event.button.id == "recover":
            # Hide recover button to prevent multiple clicks
            self.recover.visible = False

            # Start actual recovery process
            await self.app.push_screen(RecoverySetupDialog(self.comm_params), self.on_do_recovery)

    def on_do_recovery(self, result: Dict | None):
        # Is the map empty?
        if result is None:
            # User cancelled
            self.dismiss(None)
            return

        # Start recovery process with provided parameters
        self.modbus_agent.request(
            WriteHoldingRegisters(
                RECOVERY_ID,
                self.on_recovery_write_confirmed,
                address=self.rh.config_address,
                values=self.rh.ready_values(result),
                on_error=self.on_recovery_write_failed,
                on_no_response=self.on_recovery_write_failed,
                on_comm_loss=self.on_recovery_write_failed
            )
        )

    def on_recovery_write_confirmed(self, what):
        self.dismiss(None)

    def on_recovery_write_failed(self):
        self.query_one("#recovery-dialog").border_title = "Recovery Mode: Write failed"
        info_label = self.query_one("#recovery-info", Label)
        info_label.update(
            f"[red]✗ Recovery write failed![/red]\n"
            f"Please try again or consult the device manual."
        )
        self.query_one("#recover", Button).visible = False
        self.query_one("#cancel", Button).label = "Close"

    async def on_recovery_failed(self):
        info_label = self.query_one("#recovery-info", Label)
        info_label.update(
            f"[red]✗ Recovery failed![/red]\n"
            f"Please try again or consult the device manual."
        )
        self.query_one("#recovery-dialog").border_title = "Recovery Mode: Failed"

        # Rename cancel button to close
        cancel_button = self.query_one("#cancel", Button)
        cancel_button.label = "Close"
        self.recover.visible = False

    async def on_recovery_write_confirmed(self):
        info_label = self.query_one("#recovery-info", Label)
        info_label.update(
            f"[green]✓ Recovery successful![/green]\n"
            f"The device is ready to use.\n"
        )
        self.query_one("#recovery-dialog").border_title = "Recovery Mode: Success"

        # Rename cancel button to close
        cancel_button = self.query_one("#cancel", Button)
        cancel_button.label = "Close"
        self.recover.visible = False

    async def on_mount(self):
        self.query_one("#recovery-dialog").border_title = "Searching for device in recovery mode"

        # Initialize start time
        self.start_time = time.time()

        # Start the recovery modbus agent
        self._worker = self.run_worker(
            self.modbus_agent.run_async(), name="modbus_recovery_agent"
        )

    def query_info(self):
        # Make an MEI request to the recovery ID to see if a device is there
        self.modbus_agent.request(
            ReadDeviceInformation(
                RECOVERY_ID,
                self.on_device_information,
                on_error=self.on_error,
                on_no_response=self.on_no_reply,
                read_code=0x03
            )
        )

    def on_connection_status(self, status):
        """Handle connection status changes (not used here)"""
        self.query_one("#recovery-dialog").border_title = (
            f"Recovery Mode: Connection down" if not status else f"Recovery Mode: Connected"
        )

        if status:
            # Start querying for device info
            self.query_info()

    async def on_error(self, exception_code):
        """Handle scanner error by scheduling a retry."""
        info_label = self.query_one("#recovery-info", Label)
        loading = self.query_one("#loading", LoadingIndicator)
        loading.visible = False

        info_label.update(
            f"[green]✓ Found a device![/green]\n"
            f"[red]✗ This device does not support recovery mode.[/red]\n"
            f"Please check the device manual for recovery procedures."
        )

        self.query_one("#recovery-dialog").border_title = "Recovery Mode: Not supported"

    async def on_no_reply(self):
        """Handle scanner retry logic with timeout"""
        if not self.start_time:
            self.start_time = time.time()

        elapsed = time.time() - self.start_time

        if elapsed >= self.retry_timeout:
            # Give up after timeout
            info_label = self.query_one("#recovery-info", Label)
            loading = self.query_one("#loading", LoadingIndicator)
            loading.visible = False

            info_label.update(
                f"[red]✗ No device found after {int(elapsed)} seconds.[/red]\n\n"
                f"Device scan timed out. Please ensure:\n"
                f"• Device is powered on and in recovery mode\n"
                f"• EStop button was held until LEDs started flashing\n"
                f"• RS485 connection is correct\n"
                f"• Communication settings match the device"
            )

            self.query_one("#recovery-dialog").border_title = "Recovery Mode: Timeout"
            return

        # Schedule next retry
        remaining = int(self.retry_timeout - elapsed)
        self.attempt_count += 1

        # Update status during retry
        info_label = self.query_one("#recovery-info", Label)
        info_label.update(
            f"[blue]◯ Searching for device... (attempt {self.attempt_count})[/blue]\n"
            f"[dim]Time remaining: {remaining} seconds[/dim]\n\n"
            f"Make sure device is in recovery mode:\n"
            f"• Hold EStop button until all LEDs flash\n"
            f"• Device should be at address {RECOVERY_ID}"
        )

        self.query_one("#recovery-dialog").border_title = f"Recovery Mode: Searching... ({remaining}s left)"

        # Wait retry interval then restart scanner
        await asyncio.sleep(self.retry_interval)

        # Try again!
        self.query_info()

    async def on_device_information(self, pdu: ReadDeviceInformationResponse):
        """ Callback from ReadDeviceInformation """
        self.rh = RecoveryHelper(self, pdu)

        info_label = self.query_one("#recovery-info", Label)
        loading = self.query_one("#loading", LoadingIndicator)

        # Device found and identified - stop retrying
        loading.visible = False

        if self.rh.info["supported"]:
            self.query_one("#recovery-dialog").border_title = (
                f"Recovery Mode: Recoverable device found"
            )

            # Device supports recovery - show recover button and update info
            self.last_message = [
                f"[green]✓ Device Found:[/green] {self.rh.product_code}",
                f"[blue]Version:[/blue] {self.rh.model_name}",
                f"[green]✓ Recovery Supported:[/green] Version {self.rh.version}",
                f"[yellow]Recovering device current configuration...[/yellow]"
            ]

            info_label.update("\n".join(self.last_message))

            await asyncio.sleep(1)

            def on_error(self, errCode: str):
                self.on_error(f"Failed to read recovery config: Got code {errCode}")

            def on_no_response(self):
                self.on_error("Failed to read recovery config: No response from device")

            def on_comm_loss(self):
                self.on_error("Failed to read recovery config: Communication lost with device")

            # Query the device configuration now we know the address
            self.modbus_agent.request(
                ReadHoldingRegisters(
                    RECOVERY_ID,
                    self.rh.on_config_result,
                    address=self.rh.config_address,
                    count=self.rh.count,
                    on_error=on_error,
                    on_no_response=on_no_response,
                    on_comm_loss=on_comm_loss
                )
            )
        else:
            self.query_one("#recovery-dialog").border_title = f"Recovery Mode: Not possible"

            # Device identified but doesn't support recovery
            info_label.update(
                f"[green]✓ Device Found:[/green] {self.rh.device_name}\n"
                f"[blue]Type:[/blue] {self.rh.device_type}\n"
                f"[red]✗ This device does not support recovery mode.[/red]\n"
                f"Please check the device manual for recovery procedures."
            )

    def on_comm_params(self, comm_params: CommParams):
        border = self.query_one("#recovery-dialog")
        info_label = self.query_one("#recovery-info", Label)
        self.comm_params = comm_params

        # Parse configuration values
        if len(comm_params.error_message) > 0:
            border.border_title = f"Recovery Mode: Invalid config"
            self.last_message[-1] = "[red]✗ Failed to decode device configuration.[/red]"
            for err in comm_params.error_message:
                self.last_message.append(f"[red]✗ {err}[/red]")
            info_label.update("\n".join(self.last_message))
        else:
            border.border_title = f"Recovery Mode: Ready to recover"
            self.last_message[-1] = (
                f"[blue]Device normally found at:[/blue] {comm_params.device_id}"
            )
            self.last_message.append(
                f"[blue]Serial Parameters:[/blue] {comm_params.composite_serial_params()}"
            )

            info_label.update("\n".join(self.last_message))
            self.recover.visible = True

class RecoverySetupDialog(ModalScreen):
    CSS_PATH = "css/recovery_setup_dialog.tcss"

    def __init__(self, comm_params: CommParams):
        super().__init__()
        self.comm_params = comm_params

    def compose(self):
        with VerticalScroll(id="recovery-setup-dialog"):
            with Horizontal():
                yield Label("Device ID")
                yield Input(placeholder="1-247", id="device_id_input", value=str(self.comm_params.device_id))
            with Grid(id="serial-config-grid"):
                yield Label("Baud Rate", classes="select-label")
                yield Select(
                    [(str(b), b) for b in VALID_BAUD_RATES],
                    allow_blank=False,
                    value=self.comm_params.baudrate,
                    id="baud", classes="dialog-select"
                )
                yield Label(
                    f"\\[App: {config['baud']}]",
                    id="baud_label", classes="current-config-label"
                )

                yield Label("Stop Bits", classes="select-label")
                yield Select(
                    [("1", 1), ("2", 2)],
                    value=self.comm_params.stop_bits,
                    allow_blank=False,
                    id="stop",
                    classes="dialog-select"
                )
                yield Label(
                    f"\\[App: {config['stop']}]",
                    id="stop_label", classes="current-config-label"
                )

                yield Label("Parity", classes="select-label")
                yield Select(
                    [("None", 'N'), ("Even", 'E'), ("Odd", 'O')],
                    value=self.comm_params.parity,
                    allow_blank=False,
                    id="parity",
                    classes="dialog-select"
                )
                yield Label(
                    f"App: \\[parity_to_string({config['parity']})]",
                    id="parity_label", classes="current-config-label"
                )
            with Horizontal():
                yield Label("Synchronize with app", classes="sync-with-app-label")
                yield Switch(id="sync-with-app-switch")
            with Horizontal():
                yield Button("Apply and exit recovery", id="apply_exit", variant="success")
                yield Button("Cancel", id="cancel")

    def on_mount(self):
        self.query_one("#recovery-setup-dialog").border_title = "Recovery Device Configuration"

        # Set initial switch state and sync values
        sync_switch = self.query_one("#sync-with-app-switch", Switch)
        sync_switch.value = False  # Start with device settings

        # Validate initial device ID
        self._validate_device_id()

        # Start scanning for ports if none are found
        if not config.list_comports():
            self._scan_timer = self.set_interval(1.0, self._scan_ports, pause=False)

    def _validate_device_id(self) -> bool:
        """Validate device ID input and enable/disable Apply button"""
        device_id_input = self.query_one("#device_id_input", Input)
        apply_button = self.query_one("#apply_exit", Button)

        try:
            device_id = int(device_id_input.value)
            if 1 <= device_id < RECOVERY_ID:
                # Valid device ID
                device_id_input.remove_class("invalid")
                apply_button.disabled = False
                return True
            else:
                # Out of range
                device_id_input.add_class("invalid")
                apply_button.disabled = True
                return False
        except (ValueError, TypeError):
            # Not a valid integer
            device_id_input.add_class("invalid")
            apply_button.disabled = True
            return False

    def _sync_with_app_config(self, sync: bool):
        """Sync select values with app config or restore device values"""
        baud_select = self.query_one("#baud", Select)
        stop_select = self.query_one("#stop", Select)
        parity_select = self.query_one("#parity", Select)

        # Update labels to show source
        baud_label = self.query_one("#baud_label", Label)
        stop_label = self.query_one("#stop_label", Label)
        parity_label = self.query_one("#parity_label", Label)

        if sync:
            # Use app config values
            baud_select.value = config['baud']
            stop_select.value = config['stop']
            parity_select.value = config['parity']

            # Update labels to show device values
            baud_label.update(f"\\[Device: {self.comm_params.baudrate}]")
            stop_label.update(f"\\[Device: {self.comm_params.stop_bits}]")
            parity_label.update(f"\\[Device: {parity_to_string(self.comm_params.parity)}]")
        else:
            # Use device values
            baud_select.value = self.comm_params.baudrate
            stop_select.value = self.comm_params.stop_bits
            parity_select.value = self.comm_params.parity

            # Update labels to show app values
            baud_label.update(f"\\[App: {config['baud']}]")
            stop_label.update(f"\\[App: {config['stop']}]")
            parity_label.update(f"\\[App: {parity_to_string(config['parity'])}]")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Validate device ID when input changes"""
        if event.input.id == "device_id_input":
            self._validate_device_id()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle sync switch toggle"""
        if event.switch.id == "sync-with-app-switch":
            self._sync_with_app_config(event.value)

    def on_button_pressed(self, event):
        if event.button.id == "apply_exit":
            # Only proceed if device ID is valid
            if not self._validate_device_id():
                return

            # Gather parameters
            device_id = int(self.query_one("#device_id_input", Input).value)
            baudrate = int(self.query_one("#baud", Select).value)
            stopbits = int(self.query_one("#stop", Select).value)
            parity = self.query_one("#parity", Select).value
            sync_with_app = self.query_one("#sync-with-app-switch", Switch).value

            # Prepare result
            result = {
                "device_id": device_id,
                "baudrate": baudrate,
                "stopbits": stopbits,
                "parity": parity,
            }

            # Dismiss with result
            self.dismiss(result)
        else:
            # Cancel
            self.dismiss(None)
