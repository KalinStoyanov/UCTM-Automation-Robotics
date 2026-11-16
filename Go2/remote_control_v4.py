import asyncio
import time

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl


WATCHDOG_TIMEOUT = 0.5
MAX_LINEAR_SPEED = 0.20    # m/s
MAX_ANGULAR_SPEED = 0.30   # rad/s

kb = KeyBindings()

status = "READY"
vx = 0.0
wz = 0.0
last_motion_input = None
# Measured velocities (not available until robot connection)
measured_vx = None
measured_vy = None
measured_wz = None


def update(command, linear, angular, motion=False):
    global status, vx, wz, last_motion_input

    linear = max(-MAX_LINEAR_SPEED, min(MAX_LINEAR_SPEED, linear))
    angular = max(-MAX_ANGULAR_SPEED, min(MAX_ANGULAR_SPEED, angular))

    status = command
    vx = linear
    wz = angular

    if motion:
        last_motion_input = time.monotonic()
    else:
        last_motion_input = None

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
        "No commands are sent to the robot."
    )

app = Application(
    layout=Layout(Window(FormattedTextControl(screen))),
    key_bindings=kb,
    full_screen=True,
)


async def main():
    task = asyncio.create_task(watchdog())

    try:
        await app.run_async()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        update("STOP", 0.0, 0.0)


if __name__ == "__main__":
    asyncio.run(main())

