import math
import asyncio
import time

from core.communication.go2_transport import make_move, make_stop
from core.communication import go2_webrtc as transport
from core.communication.go2_webrtc import Go2WebRTC

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
    if not transport.LIVE_ENABLED:
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
        self.recovery_authorized = False

    def submit(self, linear, angular):
        linear = float(linear)
        angular = float(angular)

        if not math.isfinite(linear) or not math.isfinite(angular):
            raise ValueError("Velocity values must be finite")

        linear = max(
            -MAX_LINEAR_SPEED,
            min(MAX_LINEAR_SPEED, linear),
        )
        angular = max(
            -MAX_ANGULAR_SPEED,
            min(MAX_ANGULAR_SPEED, angular),
        )

        is_stop = linear == 0.0 and angular == 0.0

        if (self.fault or self.stop_in_progress) and not is_stop:
            return None

        if is_stop:
            self.recovery_authorized = False

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
        self.recovery_authorized = False

    def recovery_ready(self):
        """Check local queue readiness for recovery."""
        return (
            not self.stop_in_progress
            and self.pending is None
        )

    def authorize_recovery(self):
        """Record explicit recovery authorization."""
        if not self.fault or not self.recovery_ready():
            return False

        self.recovery_authorized = True
        return True

    def clear_fault(self):
        """Clear FAULT only after authorized recovery."""
        if not self.recovery_ready():
            return False

        if not self.recovery_authorized:
            return False

        self.fault = False
        self.recovery_authorized = False
        return True


command_queue = CommandQueue()

from core.safety.obstacle import ObstacleSafetyFilter

obstacle_safety = ObstacleSafetyFilter()
obstacle_latched = False
active_velocity = (0.0, 0.0)
active_dispatch_task = None
stop_generation = 0
stop_confirmed = False


def obstacle_stop(reason="STOPPED_OBSTACLE"):
    """Latch stop and discard pending movement."""
    global obstacle_latched, active_velocity, status, vx, wz
    global stop_generation, stop_confirmed

    stop_confirmed = False
    stop_generation += 1
    obstacle_latched = True
    active_velocity = (0.0, 0.0)

    if active_dispatch_task is not None:
        if not active_dispatch_task.done():
            if not command_queue.stop_in_progress:
                active_dispatch_task.cancel()

    command_queue.pending = None

    if not command_queue.stop_in_progress:
        command_queue.submit(0.0, 0.0)
    status = reason
    vx = 0.0
    wz = 0.0


def observe_obstacle(clearance):
    """Accept normalized clearance from a future LiDAR adapter."""
    valid = obstacle_safety.observe(clearance)

    candidates = [active_velocity]

    pending = command_queue.pending
    if pending is not None:
        _, linear, angular = pending
        candidates.append((linear, angular))

    for linear, angular in candidates:
        if linear == 0.0 and angular == 0.0:
            continue

        if not obstacle_safety.safe(linear, 0.0, angular):
            reason = (
                "STOPPED_OBSTACLE"
                if obstacle_safety.fresh()
                else "SENSOR_FAULT"
            )
            obstacle_safety.state = reason
            obstacle_stop(reason)
            break

    return valid


def guarded_submit(linear, angular):
    """Only a fresh explicit command may release obstacle latch."""
    global obstacle_latched
    if linear == 0.0 and angular == 0.0:
        return command_queue.submit(0.0, 0.0)

    if not obstacle_safety.safe(linear, 0.0, angular):
        obstacle_stop(
            "STOPPED_OBSTACLE" if obstacle_safety.fresh()
            else "SENSOR_FAULT"
        )
        return None

    if obstacle_latched:
        if not stop_confirmed:
            return None
        if command_queue.fault or command_queue.stop_in_progress:
            return None
        if command_queue.pending is not None:
            return None
        obstacle_latched = False

    return command_queue.submit(linear, angular)


async def obstacle_monitor():
    """Monitor last accepted motion after its dispatch."""
    while True:
        await asyncio.sleep(0.02)
        linear, angular = active_velocity
        if linear == 0.0 and angular == 0.0:
            continue
        if not obstacle_safety.safe(linear, 0.0, angular):
            obstacle_stop(
                "STOPPED_OBSTACLE" if obstacle_safety.fresh()
                else "SENSOR_FAULT"
            )




async def command_worker():
    """Execute queued commands sequentially."""
    global active_velocity, active_dispatch_task
    global stop_confirmed
    while True:
        command = command_queue.take()

        if command is None:
            await asyncio.sleep(0.01)
            continue

        sequence, linear, angular = command
        is_stop = linear == 0.0 and angular == 0.0

        try:
            if not is_stop:
                if obstacle_latched or not obstacle_safety.safe(
                    linear, 0.0, angular
                ):
                    obstacle_stop(
                        "STOPPED_OBSTACLE"
                        if obstacle_safety.fresh()
                        else "SENSOR_FAULT"
                    )
                    continue
                active_velocity = (linear, angular)
            else:
                active_velocity = (0.0, 0.0)

            generation = stop_generation
            active_dispatch_task = asyncio.create_task(
                dispatch_command(linear, angular)
            )

            try:
                await active_dispatch_task
                if is_stop:
                    stop_confirmed = True
            except asyncio.CancelledError:
                if not is_stop and generation != stop_generation:
                    continue
                command_queue.set_fault()
                raise
            finally:
                active_dispatch_task = None

        except asyncio.CancelledError:
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
    if transport.LIVE_ENABLED:
        raise RuntimeError(
            "LIVE keyboard dispatch is not enabled"
        )

    return guarded_submit(linear, angular)


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
        accepted = schedule_command(vx, wz)
        if accepted is None and (linear != 0.0 or angular != 0.0):
            vx = 0.0
            wz = 0.0
            last_transport_request = make_stop()
            if obstacle_latched:
                status = obstacle_safety.state
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
    obstacle_task = asyncio.create_task(obstacle_monitor())

    try:
        await app.run_async()
    finally:
        watchdog_task.cancel()
        worker_task.cancel()
        obstacle_task.cancel()

        await asyncio.gather(
            watchdog_task,
            worker_task,
            obstacle_task,
            return_exceptions=True,
        )

        # Discard any pending movement.
        command_queue.pending = None

        update("STOP", 0.0, 0.0, dispatch=False)

        # Process final STOP with a bounded timeout.
        try:
            await asyncio.wait_for(
                dispatch_command(0.0, 0.0),
                timeout=2.0,
            )
        except asyncio.CancelledError:
            command_queue.set_fault()
            print("FAULT: final STOP cancelled")
            raise
        except asyncio.TimeoutError:
            command_queue.set_fault()
            print("FAULT: final STOP timed out")
        except Exception as exc:
            command_queue.set_fault()
            print(f"FAULT: final STOP failed: {exc}")


if __name__ == "__main__":
    asyncio.run(main())

