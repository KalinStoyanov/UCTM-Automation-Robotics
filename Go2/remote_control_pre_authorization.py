import asyncio
import time

from go2_transport import make_move, make_stop
from go2_webrtc import Go2WebRTC, LIVE_ENABLED

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl


WATCHDOG_TIMEOUT = 0.5
MAX_LINEAR_SPEED = 0.20    # m/s
MAX_ANGULAR_SPEED = 0.30   # rad/s

kb = KeyBindings()
webrtc = Go2WebRTC()

status = "READY"
vx = 0.0
wz = 0.0
last_motion_input = None
last_transport_request = None
# Measured velocities (not available until robot connection)
measured_vx = None
measured_vy = None
measured_wz = None


async def dispatch_command(linear, angular):
    """Prepare or transmit a velocity command."""
    if not LIVE_ENABLED:
        if linear == 0.0 and angular == 0.0:
            return make_stop()
        return make_move(linear, 0.0, angular)

    if linear == 0.0 and angular == 0.0:
        return await webrtc.stop()

    return await webrtc.send_move(linear, 0.0, angular)


class CommandQueue:
    """Keep only the newest pending velocity command."""

    def __init__(self):
        self.pending = None
        self.sequence = 0
        self.fault = False
        self.stop_in_progress = False

    def submit(self, linear, angular):
        linear = float(linear)
        angular = float(angular)

        is_stop = linear == 0.0 and angular == 0.0

        if (self.fault or self.stop_in_progress) and not is_stop:
            return None

        if self.pending is not None:
            _, pending_linear, pending_angular = self.pending
            pending_stop = (
                pending_linear == 0.0
                and pending_angular == 0.0
            )

            if pending_stop and not is_stop:
                return None

        self.sequence += 1
        self.pending = (
            self.sequence,
            linear,
            angular,
        )
        return self.sequence

    def take(self):
        command = self.pending
        self.pending = None

        if command is not None:
            _, linear, angular = command
            if linear == 0.0 and angular == 0.0:
                self.stop_in_progress = True

        return command

    def finish_stop(self):
        self.stop_in_progress = False

    def set_fault(self):
        self.fault = True
        self.pending = None

    def recovery_ready(self):
        """Check local queue readiness for recovery."""
        return (
            not self.stop_in_progress
            and self.pending is None
        )

    def clear_fault(self):
        """Clear FAULT only when the command queue is idle."""
        if not self.recovery_ready():
            return False

        self.fault = False
        return True


command_queue = CommandQueue()


async def command_worker():
    """Execute queued commands sequentially."""
    while True:
        command = command_queue.take()

        if command is None:
            await asyncio.sleep(0.01)
            continue

        sequence, linear, angular = command
        is_stop = linear == 0.0 and angular == 0.0

        try:
            await dispatch_command(linear, angular)

        except asyncio.CancelledError:
            if is_stop:
                command_queue.set_fault()
            raise

        except Exception as exc:
            command_queue.set_fault()
            print(
                f"Command {sequence} failed: {exc}"
            )
            print("FAULT: movement commands blocked")

        finally:
            if is_stop:
                command_queue.finish_stop()


def schedule_command(linear, angular):
    """Submit the latest command to the sequential worker."""
    if LIVE_ENABLED:
        raise RuntimeError(
            "LIVE keyboard dispatch is not enabled"
        )

    return command_queue.submit(linear, angular)


def update(command, linear, angular, motion=False, dispatch=True):
    global status, vx, wz, last_motion_input, last_transport_request

    linear = max(-MAX_LINEAR_SPEED, min(MAX_LINEAR_SPEED, linear))
    angular = max(-MAX_ANGULAR_SPEED, min(MAX_ANGULAR_SPEED, angular))

    status = command
    vx = linear
    wz = angular

    if linear == 0.0 and angular == 0.0:
        last_transport_request = make_stop()
    else:
        last_transport_request = make_move(linear, 0.0, angular)

    if motion:
        last_motion_input = time.monotonic()
    else:
        last_motion_input = None

    if dispatch:
        schedule_command(vx, wz)
    app.invalidate()


@kb.add("up")
def forward(event):
    update("FORWARD", 0.20, 0.0, motion=True)


@kb.add("down")
def backward(event):
    update("BACKWARD", -0.20, 0.0, motion=True)


@kb.add("left")
def left(event):
    update("TURN LEFT", 0.0, 0.30, motion=True)


@kb.add("right")
def right(event):
    update("TURN RIGHT", 0.0, -0.30, motion=True)


@kb.add("space")
@kb.add("0")
def stop(event):
    update("STOP", 0.0, 0.0)


@kb.add("escape")
def exit_control(event):
    update("STOP", 0.0, 0.0)
    event.app.exit()


async def watchdog():
    global last_motion_input

    while True:
        await asyncio.sleep(0.05)

        if last_motion_input is None:
            continue

        elapsed = time.monotonic() - last_motion_input

        if elapsed >= WATCHDOG_TIMEOUT:
            update("STOP (WATCHDOG)", 0.0, 0.0)


def format_linear(value):
    if value is None:
        return "N/A"
    return f"{value:+.2f} m/s | {value * 3.6:+.2f} km/h"


def format_angular(value):
    if value is None:
        return "N/A"
    return f"{value:+.2f} rad/s | {value * 180 / 3.141592653589793:+.2f} deg/s"


def screen():
    return (
        "UNITREE GO2 AIR - REMOTE CONTROL\n"
        "MODE: SIMULATION\n\n"
        "UP: Forward       DOWN: Backward\n"
        "LEFT: Turn left   RIGHT: Turn right\n"
        "0 / Space: Stop   Esc: Exit\n\n"

        f"Last command: {status}\n\n"

        "COMMANDED VELOCITIES\n"
        f"Forward velocity: {format_linear(vx)}\n"
        f"Turning velocity: {format_angular(wz)}\n\n"

        "MEASURED VELOCITIES\n"
        f"Forward velocity: {format_linear(measured_vx)}\n"
        f"Lateral velocity: {format_linear(measured_vy)}\n"
        f"Turning velocity: {format_angular(measured_wz)}\n\n"

        "Watchdog timeout: 0.5 s\n"
        f"Transport API: "
        f"{last_transport_request['options']['api_id'] if last_transport_request else 'N/A'}\n"
        "No commands are sent to the robot."
    )

app = Application(
    layout=Layout(Window(FormattedTextControl(screen))),
    key_bindings=kb,
    full_screen=True,
)


async def main():
    watchdog_task = asyncio.create_task(watchdog())
    worker_task = asyncio.create_task(command_worker())

    try:
        await app.run_async()
    finally:
        watchdog_task.cancel()
        worker_task.cancel()

        await asyncio.gather(
            watchdog_task,
            worker_task,
            return_exceptions=True,
        )

        # Discard any pending movement.
        command_queue.pending = None

        update("STOP", 0.0, 0.0, dispatch=False)

        # Process final STOP before exiting.
        await dispatch_command(0.0, 0.0)


if __name__ == "__main__":
    asyncio.run(main())

