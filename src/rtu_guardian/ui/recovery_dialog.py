import asyncio
import time

from textual.screen import ModalScreen
from textual.widgets import Button, LoadingIndicator, Label
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive

from rtu_guardian.constants import RECOVERY_ID

from rtu_guardian.modbus.agent import ModbusAgent
from rtu_guardian.modbus.request import ReadDeviceInformation


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

class RecoveryScanningDialog(ModalScreen):
    """Dialog to scan for a device in recovery mode and optionally start recovery."""
    CSS_PATH = "css/recovery_dialog.tcss"

    def __init__(self):
        super().__init__()

        # Send requests to the agent
        self.requests = asyncio.Queue()
        # Create a Modbus agent in recovery mode
        self.modbus_agent = ModbusAgent(self.requests, self.on_connection_status, True)
        # Start the worker to cancel on dismiss
        self._worker = None
        self._scanner_worker = None

        # Retry logic
        self.start_time = None
        self.retry_timeout = 60.0  # 1 minute timeout
        self.retry_interval = 2.0  # 2 second between retries
        self.attempt_count = 0

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
            if self._worker:
                self._worker.cancel()
            self.dismiss(None)
        elif event.button.id == "recover":
            # Start actual recovery process
            self.dismiss(True) # TODO

    async def on_mount(self):
        self.query_one("#recovery-dialog").border_title = "Searching for device in recovery mode"

        # Initialize start time
        self.start_time = time.time()

        # Start the recovery modbus agent
        self._worker = self.run_worker(
            self.modbus_agent.run_async(), name="modbus_recovery_agent"
        )

        # Delay a bit to show the screen content before starting scan
        await asyncio.sleep(1)

        # Make an MEI request to the recovery ID to see if a device is there
        self.modbus_agent.request(
            ReadDeviceInformation(RECOVERY_ID, self.on_device_information, on_no_error=self.on_no_reply, on_no_response=self.on_no_reply)
        )

    async def _retry_scanner(self):
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
        self._start_scanner()

    def on_update_status(self, state: DeviceState, status_text: str, is_final: bool):
        """Called when device scanning status changes

        :param state: The current device state
        :param status_text: Human readable status message
        :param is_final: Whether this is a final state (no more updates expected)
        """
        # Update border title with current status
        elapsed = int(time.time() - self.start_time) if self.start_time else 0
        self.query_one("#recovery-dialog").border_title = f"Recovery Mode: {status_text} ({elapsed}s)"

        info_label = self.query_one("#recovery-info", Label)
        loading = self.query_one("#loading", LoadingIndicator)

        if is_final:
            if state == DeviceState.IDENTIFIED:
                # Device found and identified - stop retrying
                loading.visible = False
                device_name = self.scanner.device_name or "Unknown Device"
                device_type = self.scanner.device_type or "Unknown Type"

                if self.scanner.supports_recovery:
                    # Device supports recovery - show recover button and update info
                    recovery_info = self.scanner.recovery_info
                    version = recovery_info.get("version", "unknown") if recovery_info else "unknown"

                    info_label.update(
                        f"[green]✓ Device Found:[/green] {device_name}\n"
                        f"[blue]Type:[/blue] {device_type}\n"
                        f"[blue]Recovery Support:[/blue] Version {version}\n"
                        f"[blue]Time taken:[/blue] {elapsed} seconds\n\n"
                        f"[yellow]Click 'Recover' to start the recovery process.[/yellow]"
                    )
                    self.recover.visible = True
                else:
                    # Device identified but doesn't support recovery
                    info_label.update(
                        f"[green]✓ Device Found:[/green] {device_name}\n"
                        f"[blue]Type:[/blue] {device_type}\n"
                        f"[red]✗ This device does not support recovery mode.[/red]\n"
                        f"[blue]Time taken:[/blue] {elapsed} seconds\n\n"
                        f"Please check the device manual for recovery procedures."
                    )

            elif state == DeviceState.UNKNOWN:
                # Device found but unknown - stop retrying
                loading.visible = False
                info_label.update(
                    f"[yellow]⚠ Device found but type unknown.[/yellow]\n"
                    f"[blue]Time taken:[/blue] {elapsed} seconds\n\n"
                    f"The device responded but could not be identified.\n"
                    f"Recovery may not be possible for this device type."
                )

            elif state == DeviceState.NO_REPLY:
                # No reply - schedule retry if within timeout
                self.run_worker(self._retry_scanner(), name="retry_scanner")

        else:
            # Update info during scanning (intermediate states)
            remaining = int(self.retry_timeout - elapsed) if self.start_time else self.retry_timeout
            info_label.update(
                f"[blue]◯ {status_text}[/blue]\n"
                f"[dim]Time remaining: {max(0, remaining)} seconds[/dim]"
            )

